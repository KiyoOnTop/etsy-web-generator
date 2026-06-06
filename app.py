import base64
import io
import json
import re
import zipfile
from typing import Dict, List

import requests
import streamlit as st
from bs4 import BeautifulSoup
from openai import OpenAI
from PIL import Image

st.set_page_config(page_title="Etsy Generator V25", page_icon="✨", layout="wide")

st.markdown("""
<style>
:root { --bg:#f7f1ea; --card:#fffaf4; --ink:#1f1b16; --muted:#6b6258; --gold:#b8894d; --soft:#eadcc9; }
.stApp { background: linear-gradient(180deg,#fbf6ef 0%,#f4eadf 100%); color: var(--ink); }
.block-container { padding-top: 1.3rem; max-width: 1280px; }
[data-testid="stSidebar"] { background:#fff8ef; }
h1,h2,h3,p,label,span,div { color: var(--ink); }
.hero { background: linear-gradient(135deg,#fffaf4,#ead9c5); border:1px solid #e0c8a7; border-radius:28px; padding:28px 32px; margin-bottom:22px; box-shadow:0 12px 35px rgba(120,80,30,.08); }
.hero h1 { margin:0; font-size:2.2rem; }
.hero p { color:var(--muted); font-size:1.05rem; }
.card { background:var(--card); border:1px solid #e7d8c5; border-radius:22px; padding:20px; box-shadow:0 8px 24px rgba(60,40,20,.06); margin-bottom:18px; }
.badge { display:inline-block; padding:6px 12px; border-radius:999px; background:#f0dfca; color:#5f3d19; font-weight:700; font-size:.82rem; }
.stButton>button { background:#1f1b16 !important; color:white !important; border-radius:14px !important; border:0 !important; padding:.65rem 1rem !important; font-weight:700 !important; }
.stDownloadButton>button { background:#b8894d !important; color:white !important; border-radius:14px !important; border:0 !important; font-weight:700 !important; }
textarea,input { background:white !important; color:#111 !important; }
.stSelectbox div[data-baseweb="select"] { background:white !important; color:#111 !important; }
div[role="listbox"], div[role="option"] { background:white !important; color:#111 !important; }
.small-note { color:#796f63; font-size:.9rem; }
</style>
""", unsafe_allow_html=True)

DEFAULT_LISTING_PROMPT = """You are an Etsy SEO expert and high-converting product listing copywriter.
The final Etsy listing must be written in English.
Create a natural, persuasive, SEO-optimized listing. Avoid keyword stuffing.
Generate: SEO title under 140 characters, short description, full description, bullet points, exactly 13 Etsy tags under 20 characters each, keywords, category suggestion, suggested price, copy-paste block.
Tags must be on one line separated by commas.
Do not claim handmade unless explicitly stated.
"""

PHOTO_BASE_RULES = """Edit the provided reference image, do not create a completely unrelated product.
Keep the product 100% identical to the original reference image.
Do not modify the product shape, color, fabric, lace, patterns, stitching, accessories, proportions, prints, hardware or design.
Use a different professional model only when the image contains a model/mannequin and the selected mode allows it.
Preserve the original camera angle and product orientation.
If the source image is a back view, the result must also be a back view. Do not place a back-view product on a front-facing model.
If the source image is a side/profile view, the result must also be side/profile.
Create a realistic luxury ecommerce fashion photo with natural lighting, premium boutique decor, high-end editorial quality, no AI look, no watermark, no text, square 1:1 format.
"""

STYLE_PROMPTS = {
    "Luxury Interior": "Luxury Parisian apartment or boutique hotel interior, elegant decor, warm natural daylight, premium fashion editorial aesthetic.",
    "Romantic Boutique": "Soft romantic boutique atmosphere, elegant bedroom, subtle flowers, warm tones, cozy premium decor, natural daylight.",
    "Fashion Editorial": "High-end fashion editorial photoshoot, magazine quality, elegant posing, professional lighting, sophisticated composition.",
    "Clean Ecommerce": "Clean premium ecommerce studio, neutral beige or white background, professional softbox lighting, sharp product detail.",
}

VIEW_PROMPTS = {
    "Automatique": "Analyze the source image and preserve the same viewing angle exactly.",
    "Face": "Front view only. The model/product must face the camera like the reference front view.",
    "Dos": "Back view only. The model must be turned around; show the back of the product, never the front.",
    "Profil": "Side/profile view only. Preserve the side orientation of the reference image.",
    "Détail": "Close-up product detail view. Focus on fabric, lace, texture, seams and details exactly as in the reference.",
    "Flat lay": "Flat lay product photography. Product placed elegantly, no model, preserve product details.",
}

def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

def clean_text(text: str, limit: int = 8000) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit]

def fetch_url(url: str, scraper_key: str = ""):
    headers = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept-Language":"en-US,en;q=0.9,fr;q=0.8"}
    try:
        if scraper_key:
            r = requests.get("https://api.scraperapi.com/", params={"api_key": scraper_key, "url": url, "country_code":"us"}, timeout=75)
        else:
            r = requests.get(url, headers=headers, timeout=30)
        if r.status_code >= 400:
            return None, f"Erreur HTTP {r.status_code}"
        return r.text, None
    except Exception as e:
        return None, str(e)

def normalize_img_url(u: str) -> str:
    if not u: return ""
    u = u.replace("\\/", "/")
    if u.startswith("//"): u = "https:" + u
    if u.startswith("http://"): u = "https://" + u[7:]
    u = re.sub(r"_(\d+x\d+|\d+x\d+q\d+|\d+x\d+\.jpg).*", "", u)
    return u

def extract_images(html: str) -> List[str]:
    urls = set()
    patterns = [
        r'https?:\\?/\\?/[^"\']*alicdn[^"\']*\.(?:jpg|jpeg|png|webp)',
        r'//[^"\']*alicdn[^"\']*\.(?:jpg|jpeg|png|webp)',
        r'"imagePath"\s*:\s*"([^"]+)"',
        r'"imageUrl"\s*:\s*"([^"]+)"',
        r'"images"\s*:\s*\[(.*?)\]',
    ]
    for pat in patterns[:4]:
        for m in re.findall(pat, html, flags=re.I):
            u = normalize_img_url(m)
            if "alicdn" in u and not any(x in u.lower() for x in ["svg", "gif"]):
                urls.add(u)
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        for attr in ["src", "data-src", "data-lazy-src"]:
            u = normalize_img_url(img.get(attr, ""))
            if "alicdn" in u and re.search(r"\.(jpg|jpeg|png|webp)", u, re.I):
                urls.add(u)
    filtered = []
    for u in urls:
        low = u.lower()
        if any(bad in low for bad in ["logo", "avatar", "icon", "sprite"]):
            continue
        filtered.append(u)
    return list(dict.fromkeys(filtered))[:24]

def extract_product(html: str) -> Dict:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    desc = []
    price = ""
    if soup.title and soup.title.string: title = soup.title.string
    og = soup.find("meta", property="og:title")
    if og and og.get("content"): title = og["content"]
    md = soup.find("meta", attrs={"name":"description"}) or soup.find("meta", property="og:description")
    if md and md.get("content"): desc.append(md["content"])
    for key in ["subject", "title", "productTitle"]:
        c = re.findall(rf'"{key}"\s*:\s*"(.*?)"', html)
        if c:
            title = max(c, key=len).encode().decode("unicode_escape", errors="ignore")
    for key in ["description", "productDescription", "seoDescription"]:
        for c in re.findall(rf'"{key}"\s*:\s*"(.*?)"', html)[:5]:
            desc.append(c.encode().decode("unicode_escape", errors="ignore"))
    pc = re.findall(r'"(?:salePrice|formattedPrice|price)"\s*:\s*"?([^",}]+)', html)
    if pc: price = pc[0]
    return {"title": clean_text(title.replace("| AliExpress", "").replace("- AliExpress", "")), "description": clean_text("\n".join(desc)), "price": clean_text(price), "images": extract_images(html)}

def recommended_price(cost, shipping, margin_pct, fees_pct):
    denom = 1 - margin_pct/100 - fees_pct/100
    if denom <= .05: denom = .05
    return round((cost + shipping) / denom, 2)

def generate_listing(api_key, base_prompt, data, niche, tone, cost_price, shipping, margin, fees_pct, currency, keywords, competitor):
    client = OpenAI(api_key=api_key)
    sell_price = recommended_price(cost_price, shipping, margin, fees_pct)
    prompt = f"""
{base_prompt}

Supplier title: {data.get('title','')}
Supplier description: {data.get('description','')}
Supplier price: {data.get('price','')}
Target buyer/niche: {niche}
Tone: {tone}
SEO keywords to include naturally: {keywords}
Competitor inspiration, never copy word-for-word: {competitor}
Cost price: {cost_price} {currency}
Suggested selling price: {sell_price} {currency}

Return ONLY valid JSON with keys:
seo_title, short_description, full_description, bullet_points, tags, keywords, category_suggestion, suggested_price, copy_paste_block
"""
    res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user", "content": prompt}], temperature=.7, response_format={"type":"json_object"})
    return json.loads(res.choices[0].message.content)

def download_image(url: str):
    r = requests.get(url, timeout=30, headers={"User-Agent":"Mozilla/5.0"})
    r.raise_for_status()
    return r.content

def make_zip(files: Dict[str, bytes]) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    bio.seek(0)
    return bio.read()

def image_to_data_url(image_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(image_bytes).decode()

def generate_ai_image(api_key: str, image_url: str, prompt: str):
    client = OpenAI(api_key=api_key)
    src = download_image(image_url)
    # OpenAI image edit endpoint needs file-like image. Convert to PNG square-friendly if possible.
    img = Image.open(io.BytesIO(src)).convert("RGBA")
    max_side = 1536
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    buf.name = "reference.png"
    result = client.images.edit(model="gpt-image-1", image=buf, prompt=prompt, size="1024x1024", n=1)
    b64 = result.data[0].b64_json
    return base64.b64decode(b64)

def build_photo_prompt(view, style, custom, safe_mode=True):
    mode = """
Use a different professional model if possible while keeping the product identical and preserving the same pose direction. Do not increase nudity or make the image more revealing.
""" if not safe_mode else """
Avoid sexualized styling. Keep the outfit presentation tasteful, ecommerce-safe and non-revealing. If changing the model risks altering the product, prioritize product accuracy.
"""
    return f"""{PHOTO_BASE_RULES}

Selected view instruction:
{VIEW_PROMPTS.get(view, VIEW_PROMPTS['Automatique'])}

Selected visual style:
{STYLE_PROMPTS.get(style, STYLE_PROMPTS['Luxury Interior'])}

Safety/commercial instruction:
{mode}

Custom instruction for this specific image:
{custom}
"""

OPENAI_SECRET = get_secret("OPENAI_API_KEY", "")
SCRAPER_SECRET = get_secret("SCRAPERAPI_KEY", "")

with st.sidebar:
    st.markdown("### 🔑 Clés API")
    openai_key = st.text_input("Clé OpenAI", value=OPENAI_SECRET, type="password")
    scraper_key = st.text_input("Clé ScraperAPI", value=SCRAPER_SECRET, type="password")
    st.markdown("### 💰 Prix")
    margin = st.slider("Marge cible %", 20, 90, 45)
    shipping = st.number_input("Livraison estimée", min_value=0.0, value=0.0, step=0.5)
    fees_pct = st.slider("Frais Etsy + paiement %", 5, 30, 12)
    currency = st.selectbox("Devise", ["EUR", "USD", "GBP", "CAD", "AUD"])

st.markdown('<div class="hero"><span class="badge">V25 • Prompt par image</span><h1>✨ Générateur Etsy Premium</h1><p>Une seule page pour extraire AliExpress, créer la fiche Etsy en anglais, choisir les photos et définir un prompt différent pour chaque image.</p></div>', unsafe_allow_html=True)

# init
st.session_state.setdefault("product", {"title":"", "description":"", "price":"", "images":[]})
st.session_state.setdefault("result", None)
st.session_state.setdefault("generated_images", {})

with st.container():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("1) Extraction AliExpress")
    url = st.text_input("Lien du produit AliExpress")
    c1, c2, c3 = st.columns([1,1,2])
    with c1:
        if st.button("🔎 Extraire infos + photos"):
            if not url:
                st.warning("Colle un lien AliExpress d'abord.")
            else:
                with st.spinner("Extraction en cours..."):
                    html, err = fetch_url(url, scraper_key)
                    if err or not html:
                        st.error(f"Extraction impossible : {err}")
                    else:
                        st.session_state.product = extract_product(html)
                        st.success(f"Extraction terminée : {len(st.session_state.product.get('images', []))} photo(s) trouvée(s).")
                        st.rerun()
    with c2:
        if st.button("🧹 Réinitialiser"):
            st.session_state.product = {"title":"", "description":"", "price":"", "images":[]}
            st.session_state.result = None
            st.session_state.generated_images = {}
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

col_left, col_right = st.columns([1.05, .95])
with col_left:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("2) Informations produit")
    title = st.text_input("Titre fournisseur", value=st.session_state.product.get("title", ""))
    description = st.text_area("Description fournisseur", value=st.session_state.product.get("description", ""), height=150)
    supplier_price = st.text_input("Prix détecté", value=st.session_state.product.get("price", ""))
    cost_price = st.number_input("Prix d'achat produit", min_value=0.0, value=5.0, step=.5)
    niche = st.text_input("Niche / client cible", value="corsets, gothic fashion, romantic boutique style")
    tone = st.selectbox("Ton", ["Premium and trustworthy", "Warm and emotional", "Luxury boutique", "Gift-focused", "Minimalist and modern"])
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("3) SEO & prompt fiche")
    category = st.selectbox("Catégorie de prompt", ["Corsets", "Bijoux", "Décoration", "Animaux", "Beauté", "Mode", "Custom"])
    keywords = st.text_input("Mots-clés SEO à inclure")
    competitor = st.text_area("Fiche concurrente / inspiration optionnelle", height=80)
    base_prompt = st.text_area("Prompt de génération fiche Etsy", value=DEFAULT_LISTING_PROMPT, height=180)
    if st.button("✨ Générer la fiche Etsy"):
        if not openai_key:
            st.error("Ajoute ta clé OpenAI.")
        elif not title and not description:
            st.error("Ajoute ou extrais un titre/description.")
        else:
            with st.spinner("Génération de la fiche Etsy en anglais..."):
                try:
                    st.session_state.result = generate_listing(openai_key, base_prompt, {"title":title,"description":description,"price":supplier_price}, niche, tone, cost_price, shipping, margin, fees_pct, currency, keywords, competitor)
                    st.success("Fiche générée.")
                except Exception as e:
                    st.error(f"Erreur génération fiche : {e}")
    st.markdown('</div>', unsafe_allow_html=True)

with col_right:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("4) Résultat Etsy")
    res = st.session_state.result
    if not res:
        st.info("La fiche générée apparaîtra ici.")
    else:
        st.markdown("**Titre SEO**")
        st.code(res.get("seo_title", ""))
        st.markdown("**Description courte**")
        st.write(res.get("short_description", ""))
        st.markdown("**Tags Etsy**")
        st.code(", ".join(res.get("tags", [])))
        st.markdown("**Bloc complet à copier**")
        st.text_area("Copier-coller", value=res.get("copy_paste_block", ""), height=280)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("5) Photos AliExpress + prompt par image")
st.markdown('<p class="small-note">Chaque photo peut avoir son propre nombre de variantes, sa vue et son prompt. C’est le fonctionnement le plus proche d’une demande manuelle dans ChatGPT.</p>', unsafe_allow_html=True)
images = st.session_state.product.get("images", [])
if not images:
    st.info("Extrais d'abord un produit AliExpress pour afficher les photos.")
else:
    selected_originals = {}
    zip_originals = {}
    cols = st.columns(3)
    for i, img_url in enumerate(images):
        with cols[i % 3]:
            st.image(img_url, caption=f"Photo {i+1}", use_container_width=True)
            use = st.checkbox(f"Utiliser photo {i+1}", key=f"use_{i}", value=i < 4)
            variants = st.number_input(f"Variantes photo {i+1}", min_value=1, max_value=6, value=1, key=f"var_{i}")
            view = st.selectbox(f"Vue photo {i+1}", ["Automatique", "Face", "Dos", "Profil", "Détail", "Flat lay"], key=f"view_{i}")
            style = st.selectbox(f"Style photo {i+1}", list(STYLE_PROMPTS.keys()), key=f"style_{i}")
            safe = st.checkbox(f"Mode sécurisé photo {i+1}", key=f"safe_{i}", value=True)
            default_custom = "Keep the exact product. Change the background/decor into a realistic luxury boutique setting. Use a natural professional ecommerce look."
            custom = st.text_area(f"Prompt personnalisé photo {i+1}", value=default_custom, height=120, key=f"prompt_{i}")
            if use:
                selected_originals[i] = {"url": img_url, "variants": variants, "view": view, "style": style, "safe": safe, "custom": custom}
    b1, b2 = st.columns([1,1])
    with b1:
        if st.button("📦 Télécharger les photos AliExpress sélectionnées"):
            with st.spinner("Préparation du ZIP..."):
                files = {}
                for idx, cfg in selected_originals.items():
                    try:
                        files[f"aliexpress_photo_{idx+1}.jpg"] = download_image(cfg["url"])
                    except Exception:
                        pass
                if files:
                    st.download_button("⬇️ Télécharger ZIP AliExpress", make_zip(files), "photos_aliexpress.zip", "application/zip")
                else:
                    st.error("Impossible de télécharger les images.")
    with b2:
        if st.button("🎨 Générer les photos premium"):
            if not openai_key:
                st.error("Ajoute ta clé OpenAI.")
            elif not selected_originals:
                st.error("Sélectionne au moins une photo.")
            else:
                generated = {}
                with st.spinner("Génération des photos IA en cours..."):
                    for idx, cfg in selected_originals.items():
                        prompt = build_photo_prompt(cfg["view"], cfg["style"], cfg["custom"], cfg["safe"])
                        for n in range(int(cfg["variants"])):
                            try:
                                out = generate_ai_image(openai_key, cfg["url"], prompt)
                                generated[f"photo_{idx+1}_variant_{n+1}.png"] = out
                            except Exception as e:
                                st.warning(f"Photo {idx+1}, variante {n+1} non générée : {e}")
                st.session_state.generated_images = generated
                if generated:
                    st.success(f"{len(generated)} photo(s) générée(s).")

    gen = st.session_state.get("generated_images", {})
    if gen:
        st.markdown("### Photos premium générées")
        gcols = st.columns(3)
        for j, (name, data) in enumerate(gen.items()):
            with gcols[j % 3]:
                st.image(data, caption=name, use_container_width=True)
        st.download_button("⬇️ Télécharger les photos premium en ZIP", make_zip(gen), "photos_premium.zip", "application/zip")
st.markdown('</div>', unsafe_allow_html=True)
