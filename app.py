import base64
import io
import json
import re
import zipfile
from typing import Dict, List, Tuple

import requests
import streamlit as st
from bs4 import BeautifulSoup
from openai import OpenAI
from PIL import Image, ImageOps

st.set_page_config(page_title="Générateur Etsy SEO", page_icon="🛍️", layout="wide")

# ----------------------------- CSS -----------------------------
st.markdown(
    """
<style>
:root {
    --bg: #f7f3ee;
    --card: #ffffff;
    --text: #151515;
    --muted: #5e6673;
    --accent: #8b5cf6;
    --accent2: #111827;
    --border: #e5e7eb;
}
.stApp { background: var(--bg); color: var(--text); }
[data-testid="stSidebar"] { background: #fffaf3; border-right: 1px solid var(--border); }
.block-container { padding-top: 2rem; max-width: 1250px; }
h1,h2,h3,h4,p,div,span,label { color: var(--text) !important; }
small, .stCaption, [data-testid="stCaptionContainer"] { color: var(--muted) !important; }
.hero {
    padding: 26px 30px;
    border-radius: 24px;
    background: linear-gradient(135deg, #ffffff 0%, #fff6e8 55%, #f3e8ff 100%);
    border: 1px solid #eadfd5;
    box-shadow: 0 18px 40px rgba(17,24,39,.08);
    margin-bottom: 18px;
}
.card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 22px;
    box-shadow: 0 12px 28px rgba(17,24,39,.06);
    margin-bottom: 18px;
}
.info-box {
    background: #eef2ff;
    border: 1px solid #c7d2fe;
    border-radius: 14px;
    padding: 14px 16px;
}
.warn-box {
    background: #fff7ed;
    border: 1px solid #fed7aa;
    border-radius: 14px;
    padding: 14px 16px;
}
.ok-box {
    background: #ecfdf5;
    border: 1px solid #a7f3d0;
    border-radius: 14px;
    padding: 14px 16px;
}
.stButton > button {
    border-radius: 12px !important;
    font-weight: 700 !important;
    border: 1px solid #cbd5e1 !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #8b5cf6, #ec4899) !important;
    color: white !important;
    border: none !important;
}
/* Inputs */
.stTextInput input, .stNumberInput input, textarea {
    background: white !important;
    color: #111827 !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 12px !important;
}
/* Selectbox */
.stSelectbox div[data-baseweb="select"] > div {
    background-color: white !important;
    color: #111827 !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 12px !important;
}
.stSelectbox svg { color: #111827 !important; fill: #111827 !important; }
div[role="listbox"], ul[role="listbox"] { background: white !important; color: #111827 !important; }
div[role="option"], li[role="option"] { color: #111827 !important; background: white !important; }
div[role="option"]:hover, li[role="option"]:hover { background: #f3f4f6 !important; }
/* Tabs */
button[data-baseweb="tab"] { color: #111827 !important; font-weight: 800 !important; background: #fff !important; border-radius: 12px 12px 0 0 !important; margin-right: 6px !important; }
button[data-baseweb="tab"][aria-selected="true"] { color: #8b5cf6 !important; border-bottom: 3px solid #8b5cf6 !important; }
pre, code { color: #111827 !important; background: #f8fafc !important; border-radius: 12px !important; }
.img-card { border: 1px solid #e5e7eb; border-radius: 16px; padding: 10px; background: white; }
</style>
""",
    unsafe_allow_html=True,
)

# ----------------------------- Helpers -----------------------------
def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def clean_text(text: str, limit: int = 8000) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:limit]


def recommended_price(cost: float, shipping: float, margin_pct: int, fees_pct: int) -> float:
    denominator = 1 - (margin_pct / 100) - (fees_pct / 100)
    if denominator <= 0.05:
        denominator = 0.05
    return round((cost + shipping) / denominator, 2)


def fetch_url(url: str, scraper_key: str = "") -> Tuple[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    }
    try:
        if scraper_key:
            # Version rapide sans render=true. Beaucoup plus stable que le rendu JS complet.
            r = requests.get(
                "https://api.scraperapi.com/",
                params={"api_key": scraper_key, "url": url, "country_code": "us", "premium": "true"},
                timeout=35,
            )
        else:
            r = requests.get(url, headers=headers, timeout=20)
        if r.status_code >= 400:
            return "", f"Erreur HTTP {r.status_code}"
        return r.text, ""
    except Exception as e:
        return "", str(e)


def decode_js_string(s: str) -> str:
    try:
        return bytes(s, "utf-8").decode("unicode_escape", errors="ignore")
    except Exception:
        return s


def normalize_image_url(src: str) -> str:
    if not src:
        return ""
    src = src.strip().strip('"').strip("'")
    src = src.replace("\\/", "/")
    if src.startswith("//"):
        src = "https:" + src
    if src.startswith("http://"):
        src = "https://" + src[7:]
    # remove thumbnail suffixes when possible
    src = re.sub(r"_(\d+x\d+|\d+x\d+q\d+|\d+x\d+\.jpg).*", "", src)
    return src


def extract_product_from_html(html: str) -> Dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    desc_parts = []
    price = ""
    images: List[str] = []

    if soup.title and soup.title.string:
        title = soup.title.string
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"]

    meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    if meta_desc and meta_desc.get("content"):
        desc_parts.append(meta_desc["content"])

    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        images.append(normalize_image_url(og_img["content"]))

    text = html
    candidates = re.findall(r'"(?:subject|title|productTitle)"\s*:\s*"(.*?)"', text)
    if candidates:
        title = max([decode_js_string(c) for c in candidates], key=len)
    desc_candidates = re.findall(r'"(?:description|productDescription|seoDescription)"\s*:\s*"(.*?)"', text)
    for c in desc_candidates[:8]:
        desc_parts.append(decode_js_string(c))
    price_candidates = re.findall(r'"(?:salePrice|formattedPrice|price)"\s*:\s*"?([^",}]+)', text)
    if price_candidates:
        price = price_candidates[0]

    # Image extraction: JSON fields + <img> tags
    img_patterns = [
        r'"(?:imageUrl|imgUrl|src|poster|summImagePath|productImage)"\s*:\s*"(https?:\\?/\\?/[^" ]+)"',
        r'"(?:imageUrl|imgUrl|src|poster|summImagePath|productImage)"\s*:\s*"(//[^" ]+)"',
        r'"(?:imagePathList|images|imageUrls)"\s*:\s*\[(.*?)\]',
    ]
    for pat in img_patterns[:2]:
        for match in re.findall(pat, text):
            url = normalize_image_url(decode_js_string(match))
            if url and ("alicdn" in url or "aliexpress" in url):
                images.append(url)
    for block in re.findall(img_patterns[2], text, flags=re.S):
        for match in re.findall(r'"(https?:\\?/\\?/[^" ]+|//[^" ]+)"', block):
            url = normalize_image_url(decode_js_string(match))
            if url and ("alicdn" in url or "aliexpress" in url):
                images.append(url)

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original") or ""
        url = normalize_image_url(src)
        if url and ("alicdn" in url or "aliexpress" in url):
            images.append(url)

    # dedupe keep order
    seen = set()
    clean_images = []
    for u in images:
        if u and u not in seen and len(clean_images) < 24:
            seen.add(u)
            clean_images.append(u)

    title = clean_text(title.replace("| AliExpress", "").replace("- AliExpress", ""), 500)
    description = clean_text("\n".join(desc_parts), 8000)
    return {"title": title, "description": description, "price": clean_text(price, 80), "images": clean_images}


def generate_listing(api_key: str, data: Dict[str, str], custom_prompt: str, niche: str, tone: str, keywords: str, competitor: str, cost_price: float, shipping: float, margin: int, fees_pct: int, currency: str) -> Dict[str, object]:
    client = OpenAI(api_key=api_key)
    sell_price = recommended_price(cost_price, shipping, margin, fees_pct)
    prompt = f"""
{custom_prompt}

IMPORTANT OUTPUT RULES:
- The Etsy listing text must be in English.
- Keep the SEO title under 140 characters.
- Generate exactly 13 Etsy tags.
- Each tag must be maximum 20 characters if possible.
- Tags must be on one single line separated by commas.
- Do not claim handmade unless explicitly provided.
- Do not copy competitor text word-for-word.
- Output valid JSON only.

Supplier title:
{data.get('title','')}

Supplier description:
{data.get('description','')}

Supplier price:
{data.get('price','')}

Target buyer / niche:
{niche}

SEO keywords to include naturally:
{keywords}

Competitor / inspiration, do not copy:
{competitor}

Tone:
{tone}

Cost price:
{cost_price} {currency}

Suggested selling price:
{sell_price} {currency}

Return ONLY valid JSON with these keys:
seo_title, short_description, full_description, bullet_points, tags, keywords, category_suggestion, suggested_price, copy_paste_block
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def download_image(url: str) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=25)
    r.raise_for_status()
    return r.content


def make_square_png(image_bytes: bytes, size: int = 1024) -> bytes:
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    im = ImageOps.exif_transpose(im)
    im.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    out = io.BytesIO()
    canvas.save(out, format="PNG", quality=95)
    return out.getvalue()


def image_to_data_url(png_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("utf-8")


def generate_image_variation(api_key: str, image_bytes: bytes, prompt: str) -> bytes:
    """Creates a square edited/generated image using OpenAI Images API.
    The API may evolve; this uses the common images.edit endpoint with PNG input.
    """
    client = OpenAI(api_key=api_key)
    square_png = make_square_png(image_bytes, 1024)
    image_file = io.BytesIO(square_png)
    image_file.name = "product.png"
    result = client.images.edit(
        model="gpt-image-1",
        image=image_file,
        prompt=prompt,
        size="1024x1024",
    )
    b64 = result.data[0].b64_json
    return base64.b64decode(b64)


def make_zip(files: List[Tuple[str, bytes]]) -> bytes:
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            zf.writestr(name, data)
    mem.seek(0)
    return mem.getvalue()

# ----------------------------- Defaults -----------------------------
DEFAULT_PROMPT = """You are an Etsy SEO expert and high-converting product listing copywriter.
I run an Etsy dropshipping store. Generate a complete Etsy product listing: SEO title, warm conversion-focused description, bullet points, exactly 13 Etsy tags and useful keywords. The style must be natural, persuasive and not robotic. The output must be in English."""

CORSET_PROMPT = """You are an Etsy SEO expert and high-converting product listing copywriter.
I run an Etsy store specialized in corsets, lingerie-inspired fashion, gothic fashion, renaissance fashion, burlesque fashion, shapewear and alternative fashion. Focus on style, confidence, giftability, comfort, outfit ideas and conversion-focused Etsy SEO. The output must be in English."""

DEFAULT_PHOTO_PROMPT = """Refais ces photos de manière professionnelle et luxueuse.
Conserve fidèlement le vrai produit, ses détails, sa couleur, sa forme et sa matière.
Remplace la femme qui porte le vêtement par une autre femme professionnelle et élégante.
Format carré 1:1, lumière studio premium, style boutique de luxe, arrière-plan propre, image réaliste, haute qualité.
Ne change pas le produit vendu et n'ajoute pas de logo ni de texte."""

CATEGORY_PROMPTS = {
    "Corsets / Lingerie / Mode alternative": CORSET_PROMPT,
    "Bijoux / Accessoires": "You are an Etsy SEO expert for jewelry and fashion accessories. Write elegant, gift-focused English listings with natural SEO keywords.",
    "Décoration maison": "You are an Etsy SEO expert for home decor. Write warm, aesthetic, giftable English listings for home decoration buyers.",
    "Animaux / Pet lovers": "You are an Etsy SEO expert for pet products and gifts for pet lovers. Write friendly, emotional and search-optimized English listings.",
    "Beauté / Bien-être": "You are an Etsy SEO expert for beauty and wellness products. Write trustworthy, gentle and conversion-focused English listings.",
    "Mode générale": "You are an Etsy SEO expert for fashion products. Write stylish, natural and conversion-focused English listings.",
    "Prompt personnalisé": DEFAULT_PROMPT,
}

if "extracted" not in st.session_state:
    st.session_state.extracted = {"title": "", "description": "", "price": "", "images": []}
if "result" not in st.session_state:
    st.session_state.result = None
if "custom_prompt" not in st.session_state:
    st.session_state.custom_prompt = CORSET_PROMPT
if "photo_prompt" not in st.session_state:
    st.session_state.photo_prompt = DEFAULT_PHOTO_PROMPT
if "generated_photos" not in st.session_state:
    st.session_state.generated_photos = []

# ----------------------------- Sidebar -----------------------------
OPENAI_SECRET = get_secret("OPENAI_API_KEY", "")
SCRAPERAPI_SECRET = get_secret("SCRAPERAPI_KEY", "")

with st.sidebar:
    st.header("⚙️ Réglages")
    openai_key = st.text_input("Clé OpenAI", value=OPENAI_SECRET, type="password")
    scraperapi_key = st.text_input("Clé ScraperAPI", value=SCRAPERAPI_SECRET, type="password")
    st.markdown("<div class='info-box'>Astuce : mets tes clés dans les Secrets Streamlit pour ne plus les retaper.</div>", unsafe_allow_html=True)
    st.divider()
    st.subheader("💰 Prix")
    margin = st.slider("Marge cible", 20, 90, 45, format="%d%%")
    shipping = st.number_input("Livraison estimée", min_value=0.0, value=0.0, step=0.5)
    fees_pct = st.slider("Frais Etsy + paiement", 5, 30, 12, format="%d%%")
    currency = st.selectbox("Devise", ["EUR", "USD", "GBP", "CAD", "AUD"], index=0)

# ----------------------------- Header -----------------------------
st.markdown(
    """
<div class='hero'>
<h1>🛍️ Générateur Etsy SEO</h1>
<p>Interface en français. Les fiches Etsy générées restent en anglais pour maximiser le SEO et la conversion.</p>
<p><b>V14 :</b> extraction AliExpress + photos + prompt photo personnalisable + génération d'images carrées 1:1.</p>
</div>
""",
    unsafe_allow_html=True,
)

tab_product, tab_seo, tab_photos, tab_result = st.tabs(["1️⃣ Produit", "2️⃣ SEO & Prompt", "3️⃣ Photos", "4️⃣ Résultat"])

# ----------------------------- Product tab -----------------------------
with tab_product:
    st.markdown("<div class='card'><h3>📦 Étape 1 — Récupère ou colle les infos produit</h3><p>Colle un lien AliExpress puis essaie l’extraction. Si AliExpress bloque, colle le titre et la description manuellement.</p></div>", unsafe_allow_html=True)
    url = st.text_input("Lien AliExpress", placeholder="https://www.aliexpress.com/item/...")
    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1:
        if st.button("🔎 Extraire infos + photos", type="primary", use_container_width=True):
            if not url:
                st.warning("Colle d'abord un lien AliExpress.")
            else:
                with st.spinner("Extraction en cours..."):
                    html, err = fetch_url(url, scraperapi_key)
                    if err or not html:
                        st.error(f"Extraction impossible : {err}. Colle les infos manuellement.")
                    else:
                        data = extract_product_from_html(html)
                        if not data.get("title") and not data.get("description"):
                            st.warning("AliExpress a bloqué ou caché les données utiles. Essaie avec ScraperAPI ou colle manuellement.")
                        else:
                            st.session_state.extracted = data
                            st.success(f"Infos extraites. Photos trouvées : {len(data.get('images', []))}")
                            st.rerun()
    with c2:
        if st.button("🧹 Vider le produit", use_container_width=True):
            st.session_state.extracted = {"title": "", "description": "", "price": "", "images": []}
            st.session_state.generated_photos = []
            st.rerun()
    with c3:
        st.markdown("<div class='warn-box'>ScraperAPI est recommandé si AliExpress bloque.</div>", unsafe_allow_html=True)

    extracted = st.session_state.extracted
    left, right = st.columns([1.4, 1])
    with left:
        title = st.text_input("Titre fournisseur / AliExpress", value=extracted.get("title", ""), placeholder="Colle le titre du produit ici")
        description = st.text_area("Description fournisseur / AliExpress", value=extracted.get("description", ""), height=220, placeholder="Colle la description AliExpress ici")
    with right:
        supplier_price = st.text_input("Prix fournisseur détecté", value=extracted.get("price", ""), placeholder="Optionnel")
        cost_price = st.number_input("Prix d'achat du produit", min_value=0.0, value=5.0, step=0.5)
        sell_price = recommended_price(cost_price, shipping, margin, fees_pct)
        st.markdown(f"<div class='ok-box'><b>Prix conseillé estimé</b><br><span style='font-size:26px;font-weight:900;'>{sell_price} {currency}</span><br><small>Calculé avec marge, frais et livraison.</small></div>", unsafe_allow_html=True)

# ----------------------------- SEO tab -----------------------------
with tab_seo:
    st.markdown("<div class='card'><h3>🎯 Étape 2 — Choisis ta stratégie SEO</h3><p>Choisis une catégorie, modifie le prompt et ajoute des mots-clés si besoin.</p></div>", unsafe_allow_html=True)
    col1, col2 = st.columns([1, 1.35])
    with col1:
        category = st.selectbox("Catégorie / type de boutique", list(CATEGORY_PROMPTS.keys()))
        if st.button("Appliquer le prompt de cette catégorie", use_container_width=True):
            st.session_state.custom_prompt = CATEGORY_PROMPTS[category]
            st.success("Prompt appliqué.")
        niche = st.text_input("Client cible / niche", placeholder="Exemple : gothic fashion, gift for women, home decor")
        keywords = st.text_input("Mots-clés SEO à ajouter", placeholder="Exemple : gothic corset, waist trainer, renaissance outfit")
        tone = st.selectbox("Ton de rédaction", ["Premium and trustworthy", "Warm and emotional", "Minimalist and modern", "Gift-focused", "Luxury boutique"])
    with col2:
        st.text_area("Prompt principal modifiable", key="custom_prompt", height=220)
        competitor = st.text_area("Fiche concurrente / inspiration", placeholder="Optionnel : colle ici un titre ou une description concurrente. L’IA ne doit pas copier.", height=110)

    if st.button("✨ Générer la fiche Etsy", type="primary", use_container_width=True):
        if not openai_key:
            st.error("Ajoute ta clé OpenAI dans la barre de gauche.")
        elif not title and not description:
            st.error("Extrais ou colle au moins un titre ou une description produit.")
        else:
            with st.spinner("Génération de la fiche Etsy en anglais..."):
                try:
                    st.session_state.result = generate_listing(
                        openai_key,
                        {"title": title, "description": description, "price": supplier_price},
                        st.session_state.custom_prompt,
                        niche,
                        tone,
                        keywords,
                        competitor,
                        cost_price,
                        shipping,
                        margin,
                        fees_pct,
                        currency,
                    )
                    st.success("Fiche générée. Va dans l'onglet Résultat.")
                except Exception as e:
                    st.error(f"Génération impossible : {e}")

# ----------------------------- Photos tab -----------------------------
with tab_photos:
    st.markdown("<div class='card'><h3>🖼️ Étape 3 — Photos AliExpress + génération IA</h3><p>Les images extraites sont affichées ici. Tu peux choisir lesquelles utiliser et générer des versions carrées 1:1 avec ton prompt.</p></div>", unsafe_allow_html=True)
    st.markdown("<div class='warn-box'><b>Important :</b> garde des images fidèles au vrai produit. Évite de créer une photo trompeuse ou qui modifie le produit vendu.</div>", unsafe_allow_html=True)
    images = st.session_state.extracted.get("images", []) or []

    if not images:
        st.info("Aucune photo extraite pour l'instant. Va dans l'onglet Produit et clique sur 'Extraire infos + photos'.")
    else:
        st.write(f"Photos trouvées : **{len(images)}**")
        selected_urls = []
        cols = st.columns(4)
        for i, img_url in enumerate(images):
            with cols[i % 4]:
                st.markdown("<div class='img-card'>", unsafe_allow_html=True)
                try:
                    st.image(img_url, use_container_width=True)
                except Exception:
                    st.caption("Aperçu impossible")
                if st.checkbox(f"Utiliser photo {i+1}", value=i < 4, key=f"select_img_{i}"):
                    selected_urls.append(img_url)
                st.caption(img_url[:60] + "...")
                st.markdown("</div>", unsafe_allow_html=True)

        st.divider()
        st.subheader("Prompt photo personnalisable")
        st.text_area("Prompt utilisé pour refaire les photos", key="photo_prompt", height=170)
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            max_photos = st.number_input("Nombre max de photos à générer", min_value=1, max_value=10, value=min(4, max(1, len(selected_urls))), step=1)
        with c2:
            st.caption("Chaque image générée consomme des crédits OpenAI Images.")
        with c3:
            st.caption("Format généré : carré 1:1, 1024x1024.")

        if st.button("✨ Générer les photos modifiées", type="primary", use_container_width=True):
            if not openai_key:
                st.error("Ajoute ta clé OpenAI dans la barre de gauche.")
            elif not selected_urls:
                st.error("Sélectionne au moins une photo.")
            else:
                generated = []
                progress = st.progress(0)
                urls_to_process = selected_urls[: int(max_photos)]
                for idx, img_url in enumerate(urls_to_process):
                    try:
                        with st.spinner(f"Génération photo {idx+1}/{len(urls_to_process)}..."):
                            source_bytes = download_image(img_url)
                            edited = generate_image_variation(openai_key, source_bytes, st.session_state.photo_prompt)
                            generated.append((f"etsy_photo_ai_{idx+1}.png", edited))
                    except Exception as e:
                        st.error(f"Impossible de générer la photo {idx+1} : {e}")
                    progress.progress((idx + 1) / len(urls_to_process))
                st.session_state.generated_photos = generated
                if generated:
                    st.success(f"Photos générées : {len(generated)}")

        if selected_urls:
            raw_files = []
            if st.button("📦 Télécharger les photos AliExpress sélectionnées en ZIP", use_container_width=True):
                with st.spinner("Préparation du ZIP..."):
                    for i, u in enumerate(selected_urls):
                        try:
                            raw_files.append((f"aliexpress_photo_{i+1}.jpg", download_image(u)))
                        except Exception:
                            pass
                    if raw_files:
                        st.download_button("Télécharger le ZIP AliExpress", data=make_zip(raw_files), file_name="photos_aliexpress.zip", mime="application/zip")

    generated = st.session_state.generated_photos
    if generated:
        st.divider()
        st.subheader("Photos générées")
        cols = st.columns(4)
        for i, (name, data) in enumerate(generated):
            with cols[i % 4]:
                st.image(data, caption=name, use_container_width=True)
        st.download_button("📦 Télécharger les photos générées en ZIP", data=make_zip(generated), file_name="photos_etsy_generees.zip", mime="application/zip", use_container_width=True)

# ----------------------------- Result tab -----------------------------
with tab_result:
    st.markdown("<div class='card'><h3>✅ Résultat — Fiche Etsy générée</h3><p>Copie-colle les éléments dans Etsy. Le contenu ci-dessous est en anglais.</p></div>", unsafe_allow_html=True)
    result = st.session_state.result
    if not result:
        st.info("Aucune fiche générée pour l'instant. Va dans l'onglet SEO & Prompt puis clique sur Générer.")
    else:
        st.markdown("### SEO Title")
        st.code(result.get("seo_title", ""), language=None)
        st.markdown("### Short description")
        st.write(result.get("short_description", ""))
        st.markdown("### Full description")
        st.write(result.get("full_description", ""))
        st.markdown("### Bullet points")
        for b in result.get("bullet_points", []):
            st.write(f"• {b}")
        st.markdown("### 13 Etsy tags")
        tags = result.get("tags", [])
        if isinstance(tags, list):
            tags_line = ", ".join(tags)
        else:
            tags_line = str(tags)
        st.code(tags_line, language=None)
        st.markdown("### Keywords")
        kws = result.get("keywords", [])
        st.write(", ".join(kws) if isinstance(kws, list) else kws)
        st.markdown("### Category suggestion")
        st.write(result.get("category_suggestion", ""))
        st.markdown("### Suggested price")
        st.code(str(result.get("suggested_price", "")), language=None)
        st.markdown("### Bloc prêt à copier")
        st.text_area("Ready to copy", value=result.get("copy_paste_block", ""), height=300)
