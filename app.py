import json
import re
import io
import zipfile
import base64
import requests
from bs4 import BeautifulSoup
from PIL import Image
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Générateur Etsy Premium", page_icon="🦋", layout="wide")

# ---------- CSS premium beige / doré ----------
st.markdown("""
<style>
:root{
  --bg:#fbf8f2;
  --card:#ffffff;
  --soft:#fff7ea;
  --gold:#c99335;
  --gold2:#b98225;
  --purple:#6f55c8;
  --text:#2a221b;
  --muted:#7b6b5d;
  --border:#eadfce;
  --success:#e9f9ee;
  --success-border:#a4dfb3;
}
html, body, [class*="css"]{font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;}
.stApp{background:linear-gradient(180deg,#fffaf2 0%,#fbf8f2 45%,#f7f3ec 100%); color:var(--text);}
.block-container{padding-top:1.3rem; max-width:1520px;}
#MainMenu, footer, header{visibility:hidden;}
.hero{display:flex; justify-content:space-between; gap:20px; align-items:center; background:rgba(255,255,255,.78); border:1px solid var(--border); border-radius:24px; padding:22px 26px; margin-bottom:20px; box-shadow:0 16px 40px rgba(73,50,20,.07);}
.hero h1{font-size:34px; margin:0; letter-spacing:-.02em; color:var(--text);}
.hero p{margin:6px 0 0 0; color:var(--muted); font-size:15px;}
.logo{width:54px;height:54px;border-radius:18px;background:#f5dfbb;display:flex;align-items:center;justify-content:center;font-size:29px;box-shadow:inset 0 0 0 1px rgba(201,147,53,.25)}
.pillbar{display:flex; gap:10px; flex-wrap:wrap; margin-top:12px;}
.pill{background:#f8ead6; color:#8b5d1f; padding:8px 13px; border-radius:999px; font-weight:700; font-size:13px; border:1px solid #edd6b6;}
.top-actions{display:flex; gap:10px; align-items:center; flex-wrap:wrap; justify-content:flex-end;}
.action-pill{background:white;border:1px solid var(--border); border-radius:999px; padding:10px 14px; font-weight:700; color:#60472a; box-shadow:0 8px 18px rgba(83,55,20,.06)}
.card{background:var(--card); border:1px solid var(--border); border-radius:20px; padding:18px; box-shadow:0 12px 32px rgba(83,55,20,.06); margin-bottom:16px;}
.card-title{display:flex;align-items:center;gap:10px;font-weight:800;color:#46311e;font-size:16px;margin-bottom:12px;}
.step{background:var(--purple); color:white; border-radius:999px; width:25px; height:25px; display:inline-flex; align-items:center; justify-content:center; font-size:13px; font-weight:800;}
.step.gold{background:var(--gold);}
.help{font-size:13px;color:var(--muted);margin-top:-4px;margin-bottom:12px;}
.info-blue{background:#eef7ff;border:1px solid #cde8ff;color:#2a5c7f;border-radius:14px;padding:12px;font-size:14px;}
.success-box{background:var(--success);border:1px solid var(--success-border);color:#267241;border-radius:14px;padding:13px;margin-top:12px;font-weight:650;}
.warning-box{background:#fff4e2;border:1px solid #f0c98c;color:#83551d;border-radius:14px;padding:13px;margin-top:12px;}
.photo-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;}
.photo-card{border:2px solid transparent;border-radius:14px;overflow:hidden;background:#f6f0e8;box-shadow:0 8px 18px rgba(83,55,20,.06)}
.photo-card.selected{border-color:var(--gold)}
.photo-card img{width:100%;aspect-ratio:1/1;object-fit:cover;display:block;}
.result-img{border-radius:16px; width:100%; aspect-ratio:1/1; object-fit:cover; box-shadow:0 10px 25px rgba(0,0,0,.08); border:1px solid var(--border)}
.stButton>button{border-radius:12px !important; min-height:44px; font-weight:800 !important; border:1px solid var(--border) !important;}
.stButton>button[kind="primary"]{background:linear-gradient(135deg,var(--gold),var(--gold2)) !important; color:#fff !important; border:0 !important; box-shadow:0 10px 22px rgba(201,147,53,.24) !important;}
.stTextInput input, .stTextArea textarea, .stNumberInput input{border-radius:12px !important; border:1px solid #ddcfbc !important; background:#fff !important; color:var(--text) !important;}
.stSelectbox [data-baseweb="select"]{border-radius:12px !important; background:#fff !important; color:var(--text) !important; border:1px solid #ddcfbc !important;}
div[role="listbox"]{background:#fff !important; color:#111 !important; border:1px solid #ddcfbc !important;}
div[role="option"]{color:#111 !important; background:#fff !important;}
div[role="option"]:hover{background:#f7ead8 !important; color:#111 !important;}
.small-label{font-size:12px;font-weight:800;color:#6a5543;text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px;}
.copy-box{background:#fffaf2;border:1px solid var(--border);border-radius:16px;padding:12px;}
hr{border:0;border-top:1px solid var(--border);margin:14px 0;}
</style>
""", unsafe_allow_html=True)

# ---------- Helpers ----------
def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

OPENAI_SECRET = get_secret("OPENAI_API_KEY", "")
SCRAPERAPI_SECRET = get_secret("SCRAPERAPI_KEY", "")

DEFAULT_LISTING_PROMPT = """You are an expert Etsy SEO copywriter.
The store sells premium fashion and lifestyle products.
Generate an English Etsy listing optimized for SEO and conversion.
Keep the text natural, persuasive and not robotic.
Do not claim handmade unless explicitly stated.
Return valid JSON only."""

DEFAULT_PHOTO_PROMPT = """OBJECTIVE:
Keep EXACTLY the same product as the AliExpress reference image, but create a new realistic, professional and luxurious photo.

ABSOLUTE RULES:
- The product must remain identical: same shape, same colors, same fabric, same lace, same patterns, same stitching, same accessories, same proportions.
- Do not redesign the product.
- Do not invent or remove product details.
- Preserve the original viewing angle selected by the user.
- If the view is back view, the model must be shown from the back.
- If the view is front view, the model must be shown from the front.
- If the view is side view, the model must be shown from the side.

YOU MAY CHANGE ONLY:
- background and decor
- lighting and ambience
- model, if present
- pose, only if the product remains clearly visible and angle is respected

STYLE:
Ultra realistic professional luxury ecommerce photography, elegant boutique interior, soft natural daylight, realistic skin texture, natural model proportions, premium editorial style, no AI look.

OUTPUT:
Square 1:1, high resolution, Etsy-ready, no text, no logo, no watermark."""

CATEGORY_CONTEXTS = {
    "Corsets / Lingerie / Mode alternative": "I run an Etsy store specialized in corsets, lingerie-inspired fashion, gothic fashion, renaissance fashion, burlesque fashion, shapewear and alternative fashion.",
    "Bijoux / Accessoires": "I run an Etsy store specialized in jewelry, fashion accessories, gifts, elegant details and premium boutique-style products.",
    "Décoration maison": "I run an Etsy store specialized in home decor, cozy interiors, elegant decorative objects, gifts and aesthetic living spaces.",
    "Animaux / Pet lovers": "I run an Etsy store specialized in pet lovers, cute gifts, pet accessories and emotional gift products.",
    "Beauté / Bien-être": "I run an Etsy store specialized in beauty, wellness, self-care, spa-inspired products and giftable lifestyle items.",
    "Mode générale": "I run an Etsy store specialized in fashion, accessories, outfits and stylish giftable products.",
    "Prompt personnalisé": "Write a custom category context here."
}

# ---------- State ----------
for key, val in {
    "extracted": {"title":"", "description":"", "price":"", "images":[]},
    "selected_images": [],
    "generated_images": [],
    "result": None,
    "listing_prompt": DEFAULT_LISTING_PROMPT,
    "photo_prompt": DEFAULT_PHOTO_PROMPT,
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("### ⚙️ Clés API")
    openai_key = st.text_input("Clé OpenAI", value=OPENAI_SECRET, type="password")
    scraperapi_key = st.text_input("Clé ScraperAPI", value=SCRAPERAPI_SECRET, type="password")
    st.markdown("<div class='warning-box'>Astuce : sauvegarde tes clés dans les Secrets Streamlit pour ne plus les retaper.</div>", unsafe_allow_html=True)
    st.markdown("### 💰 Prix")
    margin = st.slider("Marge cible", 20, 90, 45)
    shipping = st.number_input("Livraison estimée", min_value=0.0, value=0.0, step=0.5)
    fees_pct = st.slider("Frais Etsy + paiement", 5, 30, 12)
    currency = st.selectbox("Devise", ["EUR", "USD", "GBP", "CAD", "AUD"], index=0)

# ---------- Core functions ----------
def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:9000]

def fetch_url(url: str, scraper_key: str = ""):
    headers = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36", "Accept-Language":"en-US,en;q=0.9,fr;q=0.8"}
    try:
        if scraper_key:
            # Fast mode: no JS render by default to avoid timeout.
            r = requests.get("https://api.scraperapi.com/", params={"api_key": scraper_key, "url": url, "country_code":"us", "premium":"true"}, timeout=35)
        else:
            r = requests.get(url, headers=headers, timeout=20)
        if r.status_code >= 400:
            return None, f"Erreur HTTP {r.status_code}"
        return r.text, None
    except Exception as e:
        return None, str(e)

def extract_images(html: str):
    urls = set()
    for m in re.findall(r'https?:\\/\\/[^"\\]+?\.(?:jpg|jpeg|png|webp)', html, flags=re.I):
        u = m.replace('\\/', '/')
        if any(x in u.lower() for x in ["alicdn", "ae01", "alicdn.com"]):
            urls.add(u)
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        for attr in ["src", "data-src"]:
            u = img.get(attr)
            if u:
                if u.startswith("//"):
                    u = "https:" + u
                if u.startswith("http") and any(x in u.lower() for x in ["alicdn", "ae01", "alicdn.com"]):
                    urls.add(u)
    clean = []
    for u in urls:
        u = re.sub(r"_(\d+x\d+|\d+x\d+q\d+)\.(jpg|jpeg|png|webp)", r".\2", u, flags=re.I)
        if u not in clean:
            clean.append(u)
    return clean[:24]

def extract_product_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    desc_parts = []
    price = ""
    if soup.title and soup.title.string:
        title = soup.title.string
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"]
    meta_desc = soup.find("meta", attrs={"name":"description"}) or soup.find("meta", property="og:description")
    if meta_desc and meta_desc.get("content"):
        desc_parts.append(meta_desc["content"])
    candidates = re.findall(r'"(?:subject|title|productTitle)"\s*:\s*"(.*?)"', html)
    if candidates:
        title = max([c.encode('utf-8').decode('unicode_escape', errors='ignore') for c in candidates], key=len)
    desc_candidates = re.findall(r'"(?:description|productDescription|seoDescription)"\s*:\s*"(.*?)"', html)
    for c in desc_candidates[:5]:
        desc_parts.append(c.encode('utf-8').decode('unicode_escape', errors='ignore'))
    price_candidates = re.findall(r'"(?:salePrice|formattedPrice|price)"\s*:\s*"?([^",}]+)', html)
    if price_candidates:
        price = price_candidates[0]
    return {"title": clean_text(title.replace("| AliExpress", "").replace("- AliExpress", "")), "description": clean_text("\n".join(desc_parts)), "price": clean_text(price), "images": extract_images(html)}

def recommended_price(cost, shipping, margin_pct, fees_pct):
    denom = 1 - (margin_pct/100) - (fees_pct/100)
    denom = max(denom, .05)
    return round((cost+shipping)/denom, 2)

def generate_listing(api_key, data, category_context, niche, seo_keywords, competitor, tone, cost_price):
    client = OpenAI(api_key=api_key)
    sell_price = recommended_price(cost_price, shipping, margin, fees_pct)
    prompt = f"""
{st.session_state.listing_prompt}

CATEGORY CONTEXT:
{category_context}

Rules:
- Text must be in English.
- Title under 140 characters.
- Exactly 13 Etsy tags, each max 20 characters when possible.
- Tags must be returned as an array and also in copy_paste_block on one comma-separated line.
- Use a warm, natural, premium tone.
- Avoid trademarked brand names unless clearly provided by the user and legally usable.
- Never copy competitor text word-for-word.

Supplier title: {data.get('title','')}
Supplier description: {data.get('description','')}
Supplier price: {data.get('price','')}
Target buyer / niche: {niche}
SEO keywords to include naturally: {seo_keywords}
Competitor inspiration, do not copy: {competitor}
Tone: {tone}
Cost price: {cost_price} {currency}
Suggested selling price: {sell_price} {currency}

Return ONLY valid JSON with keys:
seo_title, short_description, full_description, bullet_points, tags, keywords, category_suggestion, suggested_price, copy_paste_block
"""
    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}], temperature=.65, response_format={"type":"json_object"})
    return json.loads(response.choices[0].message.content)

def download_image(url):
    try:
        r = requests.get(url, timeout=18, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        return img
    except Exception:
        return None

def image_to_data_url(img: Image.Image):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def generate_photo_edit(api_key, img: Image.Image, view, style, photo_prompt):
    # Uses OpenAI image generation with reference image when available.
    # If the SDK/environment does not support edits, the app will show a clear error.
    client = OpenAI(api_key=api_key)
    angle_rule = {
        "Vue de face": "The output must be a front view. The model must face the camera.",
        "Vue de dos": "The output must be a back view. The model must be seen from the back. Do not show the product reversed on a front-facing model.",
        "Vue latérale": "The output must be a side view. Preserve the side angle.",
        "Gros plan": "The output must be a close-up product detail view. Keep details sharp.",
        "Flat lay / produit seul": "The output must be a flat lay or product-only view. Do not add a model unless necessary."
    }.get(view, "Preserve the original viewing angle.")
    full_prompt = f"""{photo_prompt}

SELECTED VIEW RULE:
{angle_rule}

SELECTED STYLE:
{style}

Important: edit the reference image, do not invent a new product."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    try:
        # OpenAI image edit endpoint style. Some accounts/SDK versions may vary.
        res = client.images.edit(model="gpt-image-1", image=("reference.png", buf, "image/png"), prompt=full_prompt, size="1024x1024")
        b64 = res.data[0].b64_json
        out = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
        return out, None
    except Exception as e:
        return None, str(e)

def make_zip_from_images(images, prefix="etsy_images"):
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, img in enumerate(images, 1):
            buf = io.BytesIO(); img.save(buf, format="PNG")
            z.writestr(f"{prefix}_{i}.png", buf.getvalue())
    zbuf.seek(0)
    return zbuf.getvalue()

# ---------- Header ----------
st.markdown("""
<div class="hero">
  <div style="display:flex;gap:16px;align-items:center;">
    <div class="logo">🦋</div>
    <div>
      <h1>Générateur de Fiches Etsy Premium</h1>
      <p>Extraction AliExpress + génération photos + fiche produit SEO en anglais.</p>
      <div class="pillbar"><span class="pill">URL AliExpress</span><span class="pill">Photos IA</span><span class="pill">Prompts sauvegardables</span><span class="pill">SEO Etsy</span></div>
    </div>
  </div>
  <div class="top-actions"><span class="action-pill">📘 Guide d'utilisation</span><span class="action-pill">🇫🇷 Français</span><span class="action-pill">🗂️ Historique / Prompts</span></div>
</div>
""", unsafe_allow_html=True)

# ---------- Layout ----------
left, mid, right = st.columns([.95, 1.05, 1.05], gap="large")

with left:
    st.markdown('<div class="card"><div class="card-title"><span class="step">1</span> EXTRAIRE DE ALIEXPRESS</div>', unsafe_allow_html=True)
    url = st.text_input("Lien AliExpress", placeholder="https://fr.aliexpress.com/item/...")
    if st.button("🔗 Extraire les informations", type="primary", use_container_width=True):
        if not url:
            st.warning("Colle d'abord un lien AliExpress.")
        else:
            with st.spinner("Extraction en cours..."):
                html, err = fetch_url(url, scraperapi_key)
                if err or not html:
                    st.error(f"Extraction impossible : {err}. Colle les infos manuellement.")
                else:
                    data = extract_product_from_html(html)
                    if not data.get("title") and not data.get("description") and not data.get("images"):
                        st.warning("AliExpress a caché les données utiles. Essaie avec ScraperAPI ou colle manuellement.")
                    else:
                        st.session_state.extracted = data
                        st.session_state.selected_images = list(range(min(4, len(data.get("images", [])))))
                        st.success(f"Extraction réussie : {len(data.get('images', []))} photo(s) récupérée(s).")
                        st.rerun()
    if st.session_state.extracted.get("title") or st.session_state.extracted.get("images"):
        st.markdown(f'<div class="success-box">Extraction réussie !<br>{len(st.session_state.extracted.get("images", []))} photo(s) récupérée(s).</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="card-title"><span class="step">🖼️</span> PHOTOS EXTRAITES</div>', unsafe_allow_html=True)
    imgs = st.session_state.extracted.get("images", [])
    if not imgs:
        st.info("Les photos extraites apparaîtront ici.")
    else:
        for row_start in range(0, min(len(imgs), 9), 3):
            cols = st.columns(3)
            for j, c in enumerate(cols):
                idx = row_start + j
                if idx < len(imgs):
                    with c:
                        st.image(imgs[idx], use_container_width=True)
                        checked = st.checkbox("Sélection", value=idx in st.session_state.selected_images, key=f"sel_{idx}")
                        if checked and idx not in st.session_state.selected_images:
                            st.session_state.selected_images.append(idx)
                        if not checked and idx in st.session_state.selected_images:
                            st.session_state.selected_images.remove(idx)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Tout sélectionner", use_container_width=True):
                st.session_state.selected_images = list(range(len(imgs)))
                st.rerun()
        with c2:
            if st.button("Vider", use_container_width=True):
                st.session_state.selected_images = []
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

with mid:
    st.markdown('<div class="card"><div class="card-title"><span class="step gold">2</span> INFORMATIONS PRODUIT</div>', unsafe_allow_html=True)
    extracted = st.session_state.extracted
    title = st.text_input("Titre du produit", value=extracted.get("title", ""), placeholder="Colle le titre AliExpress ici")
    price = st.text_input("Prix fournisseur détecté", value=extracted.get("price", ""), placeholder="Optionnel")
    description = st.text_area("Description AliExpress", value=extracted.get("description", ""), height=150, placeholder="Colle la description AliExpress ici")
    cost_price = st.number_input("Prix d'achat du produit", min_value=0.0, value=5.0, step=0.5)
    st.markdown(f"<div class='copy-box'><b>Prix conseillé estimé</b><br><span style='font-size:24px;font-weight:900;color:#3b2b1d'>{recommended_price(cost_price, shipping, margin, fees_pct)} {currency}</span><br><span style='color:#7b6b5d;font-size:13px'>Calculé avec marge, frais Etsy et livraison.</span></div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="card-title"><span class="step gold">4</span> GÉNÉRER DE NOUVELLES PHOTOS</div>', unsafe_allow_html=True)
    st.markdown('<div class="info-blue">L’IA doit garder le produit identique et changer seulement : fond, décor, mannequin si présent, éclairage et ambiance.</div>', unsafe_allow_html=True)
    view = st.selectbox("Vue de la photo sélectionnée", ["Vue de face", "Vue de dos", "Vue latérale", "Gros plan", "Flat lay / produit seul"])
    st.caption("Choisis bien la vue : si la photo est de dos, sélectionne Vue de dos pour éviter les erreurs.")
    style = st.selectbox("Style photo", ["Luxury Interior / Appartement parisien", "Romantic Boutique", "Clean Ecommerce Premium", "Fashion Editorial", "Warm Cozy Bedroom"])
    max_generate = st.selectbox("Nombre d'images à générer", [1,2,3,4], index=1)
    if st.button("✨ Générer les photos", type="primary", use_container_width=True):
        if not openai_key:
            st.error("Ajoute ta clé OpenAI dans la barre de gauche.")
        elif not st.session_state.selected_images:
            st.error("Sélectionne au moins une photo extraite.")
        else:
            generated = []
            with st.spinner("Génération des photos avec image de référence..."):
                for idx in st.session_state.selected_images[:max_generate]:
                    img = download_image(imgs[idx]) if idx < len(imgs) else None
                    if img is None:
                        st.warning(f"Impossible de télécharger l'image {idx+1}.")
                        continue
                    out, err = generate_photo_edit(openai_key, img, view, style, st.session_state.photo_prompt)
                    if err:
                        st.error(f"Erreur génération image : {err}")
                        break
                    if out:
                        generated.append(out)
            if generated:
                st.session_state.generated_images = generated
                st.success(f"{len(generated)} image(s) générée(s).")
                st.rerun()
    if st.session_state.generated_images:
        cols = st.columns(min(4, len(st.session_state.generated_images)))
        for i, img in enumerate(st.session_state.generated_images):
            with cols[i % len(cols)]:
                st.image(img, use_container_width=True)
        st.download_button("📥 Télécharger les photos générées", data=make_zip_from_images(st.session_state.generated_images, "photos_etsy"), file_name="photos_etsy_generees.zip", mime="application/zip", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

with right:
    st.markdown('<div class="card"><div class="card-title"><span class="step gold">3</span> PARAMÈTRES SEO & PROMPTS</div>', unsafe_allow_html=True)
    category = st.selectbox("Catégorie / type de boutique", list(CATEGORY_CONTEXTS.keys()))
    category_context = st.text_area("Contexte de catégorie modifiable", value=CATEGORY_CONTEXTS[category], height=95)
    niche = st.text_input("Client cible / niche", placeholder="Ex : gothic fashion, gift for women, home decor")
    seo_keywords = st.text_input("Mots-clés SEO à ajouter", placeholder="Ex : gothic corset, waist trainer, renaissance outfit")
    competitor = st.text_area("Fiche concurrente / inspiration", placeholder="Optionnel : colle ici un titre ou une description concurrente. L’IA ne doit pas copier.", height=85)
    tone = st.selectbox("Ton de rédaction", ["Premium and trustworthy", "Warm and emotional", "Luxury boutique", "Gift-focused", "Minimalist and modern"])
    with st.expander("Modifier le prompt principal SEO"):
        st.session_state.listing_prompt = st.text_area("Prompt SEO", value=st.session_state.listing_prompt, height=160)
        if st.button("Réinitialiser prompt SEO"):
            st.session_state.listing_prompt = DEFAULT_LISTING_PROMPT
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="card-title"><span class="step gold">5</span> PROMPT PHOTO PERSONNALISÉ</div>', unsafe_allow_html=True)
    st.session_state.photo_prompt = st.text_area("Prompt utilisé pour les photos", value=st.session_state.photo_prompt, height=260)
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        if st.button("Luxe & élégant"):
            st.session_state.photo_prompt += "\nLuxury elegant interior, soft daylight, expensive boutique mood."
            st.rerun()
    with cc2:
        if st.button("Romantique"):
            st.session_state.photo_prompt += "\nRomantic soft bedroom decor, flowers, warm light, feminine atmosphere."
            st.rerun()
    with cc3:
        if st.button("Réinitialiser"):
            st.session_state.photo_prompt = DEFAULT_PHOTO_PROMPT
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# Results full width
st.markdown('<div class="card"><div class="card-title"><span class="step gold">6</span> GÉNÉRER LA FICHE PRODUIT ETSY</div>', unsafe_allow_html=True)
gen_col, res_col = st.columns([.32,.68])
with gen_col:
    if st.button("✍️ Générer la fiche complète", type="primary", use_container_width=True):
        if not openai_key:
            st.error("Ajoute ta clé OpenAI dans la barre de gauche.")
        elif not title and not description:
            st.error("Ajoute ou extrais un titre / une description produit.")
        else:
            with st.spinner("Génération de la fiche Etsy en anglais..."):
                try:
                    st.session_state.result = generate_listing(openai_key, {"title":title, "description":description, "price":price}, category_context, niche, seo_keywords, competitor, tone, cost_price)
                    st.success("Fiche générée.")
                except Exception as e:
                    st.error(f"Erreur génération : {e}")
with res_col:
    result = st.session_state.result
    if not result:
        st.info("Le résultat Etsy apparaîtra ici.")
    else:
        t1,t2,t3,t4 = st.tabs(["Titre SEO", "Description SEO", "Tags SEO", "Bloc complet"])
        with t1:
            st.code(result.get("seo_title", ""), language=None)
        with t2:
            st.write(result.get("short_description", ""))
            st.write(result.get("full_description", ""))
            for b in result.get("bullet_points", []): st.write(f"• {b}")
        with t3:
            st.code(", ".join(result.get("tags", [])), language=None)
            st.write("**Mots-clés :**", ", ".join(result.get("keywords", [])) if isinstance(result.get("keywords"), list) else result.get("keywords", ""))
        with t4:
            st.text_area("Prêt à copier", value=result.get("copy_paste_block", ""), height=260)
st.markdown('</div>', unsafe_allow_html=True)
