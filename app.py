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
from PIL import Image, ImageOps, ImageEnhance

st.set_page_config(page_title="Etsy Generator Pro", page_icon="🛍️", layout="wide")

# -------------------- STYLE --------------------
st.markdown("""
<style>
:root{
  --bg:#f8f5ef;
  --card:#ffffff;
  --ink:#171717;
  --muted:#666;
  --brand:#7c3aed;
  --brand2:#a855f7;
  --line:#eadfd2;
  --soft:#fff7ed;
}
.stApp { background: var(--bg); color: var(--ink); }
.block-container { max-width: 1380px; padding-top: 1.2rem; }
h1,h2,h3,h4,p,span,label,div { color: var(--ink); }
.hero {
  background: linear-gradient(135deg, #fff, #fff7ed 55%, #f3e8ff);
  border: 1px solid var(--line);
  border-radius: 28px;
  padding: 30px 34px;
  margin-bottom: 22px;
  box-shadow: 0 18px 45px rgba(84,52,16,.08);
}
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 22px;
  margin-bottom: 18px;
  box-shadow: 0 12px 32px rgba(84,52,16,.06);
}
.small-card {
  background: var(--soft);
  border: 1px solid #fed7aa;
  border-radius: 18px;
  padding: 16px;
}
.step-badge {
  display:inline-flex;align-items:center;justify-content:center;
  background:var(--brand); color:white; width:28px;height:28px;border-radius:50%;
  font-weight:800; margin-right:8px;
}
.copybox textarea { font-family: ui-monospace, Menlo, Consolas, monospace !important; }
.stButton>button {
  border-radius: 14px !important;
  border: 1px solid #7c3aed !important;
  background: linear-gradient(135deg,#7c3aed,#a855f7) !important;
  color: white !important;
  font-weight: 800 !important;
  min-height: 44px;
}
.stButton>button[kind="secondary"]{
  background: #fff !important;
  color:#4c1d95 !important;
}
.stTextInput input, .stTextArea textarea, .stNumberInput input {
  background:white !important; color:#111 !important; border:1px solid #d6c8b8 !important; border-radius:14px !important;
}
.stSelectbox div[data-baseweb="select"] { background:white !important; color:#111 !important; border-radius:14px !important; }
div[role="listbox"] { background:white !important; color:#111 !important; }
div[role="option"] { color:#111 !important; background:white !important; }
div[role="option"]:hover { background:#f3e8ff !important; }
.stTabs [data-baseweb="tab-list"] { gap: 14px; }
.stTabs [data-baseweb="tab"] {
  background:white; border:1px solid var(--line); border-radius:999px; padding:10px 18px; color:#111 !important; font-weight:800;
}
.stTabs [aria-selected="true"] { background:#f3e8ff !important; color:#5b21b6 !important; border-color:#c084fc; }
hr { border-color: var(--line); }
img { border-radius: 14px; }
</style>
""", unsafe_allow_html=True)

# -------------------- HELPERS --------------------
def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def clean_text(text: str, limit: int = 9000) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:limit]


def recommended_price(cost: float, shipping: float, margin_pct: int, fees_pct: int) -> float:
    denominator = 1 - (margin_pct / 100) - (fees_pct / 100)
    if denominator <= 0.05:
        denominator = 0.05
    return round((cost + shipping) / denominator, 2)


def fetch_url(url: str, scraper_key: str = "") -> Tuple[str | None, str | None]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    }
    try:
        if scraper_key:
            r = requests.get(
                "https://api.scraperapi.com/",
                params={"api_key": scraper_key, "url": url, "country_code": "us", "premium": "true"},
                timeout=75,
            )
        else:
            r = requests.get(url, headers=headers, timeout=30)
        if r.status_code >= 400:
            return None, f"Erreur HTTP {r.status_code}"
        return r.text, None
    except Exception as e:
        return None, str(e)


def extract_product_from_html(html: str) -> Dict:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    desc_parts: List[str] = []
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
        images.append(og_img["content"])

    text = html
    # AliExpress often stores info in embedded JSON / escaped strings.
    title_candidates = re.findall(r'"(?:subject|title|productTitle)"\s*:\s*"(.*?)"', text)
    if title_candidates:
        title = max([bytes(c, "utf-8").decode("unicode_escape", errors="ignore") for c in title_candidates], key=len)

    desc_candidates = re.findall(r'"(?:description|productDescription|seoDescription)"\s*:\s*"(.*?)"', text)
    for c in desc_candidates[:6]:
        desc_parts.append(bytes(c, "utf-8").decode("unicode_escape", errors="ignore"))

    price_candidates = re.findall(r'"(?:salePrice|formattedPrice|price)"\s*:\s*"?([^",}]+)', text)
    if price_candidates:
        price = price_candidates[0]

    # Images: direct, escaped, and //cdn style.
    raw_imgs = re.findall(r'https?:\\?/\\?/[^"\\]+?\.(?:jpg|jpeg|png|webp)', text, flags=re.I)
    raw_imgs += re.findall(r'//[^"\']+?\.(?:jpg|jpeg|png|webp)', text, flags=re.I)
    for img in raw_imgs:
        img = img.replace("\\/", "/")
        if img.startswith("//"):
            img = "https:" + img
        if any(bad in img.lower() for bad in ["sprite", "logo", "icon", "avatar"]):
            continue
        if img not in images:
            images.append(img)

    # Keep likely product images.
    images = [i for i in images if len(i) < 600]
    images = list(dict.fromkeys(images))[:20]

    return {
        "title": clean_text(title.replace("| AliExpress", "").replace("- AliExpress", "")),
        "description": clean_text("\n".join(desc_parts)),
        "price": clean_text(price),
        "images": images,
    }


def build_default_prompt(category_context: str) -> str:
    return f"""You are an Etsy SEO expert and high-converting product listing copywriter.

Store / category context:
{category_context}

Your mission is to generate a complete Etsy product listing including:
1. One SEO-optimized Etsy title, clearly related to the product and keywords, natural, readable, and under 140 characters.
2. A warm, fluent, persuasive English description with a few relevant emojis, but not too many.
3. Exactly 13 Etsy tags, each maximum 20 characters, on one single comma-separated line.

Rules:
- The final Etsy content must be in English.
- Do not claim handmade unless the product is explicitly handmade.
- Do not copy competitor text word-for-word.
- Keep it natural, not robotic, and avoid keyword stuffing.
- Use the strongest Etsy search keywords naturally in the title and first paragraph.
- Make the listing conversion-focused and trustworthy.
"""

CATEGORY_PRESETS = {
    "Corsets / Lingerie / Mode alternative": "I run an Etsy store specialized in corsets, lingerie-inspired fashion, gothic fashion, renaissance fashion, burlesque fashion, shapewear and alternative fashion. Focus on style, confidence, giftability, comfort, outfit ideas and conversion-focused Etsy SEO.",
    "Bijoux / Accessoires": "I run an Etsy store specialized in jewelry and fashion accessories. Focus on giftability, everyday wear, elegance, style, occasions, materials, and conversion-focused Etsy SEO.",
    "Décoration maison": "I run an Etsy store specialized in home decor. Focus on cozy interiors, aesthetic rooms, gift ideas, wall decor, living room styling, and conversion-focused Etsy SEO.",
    "Animaux / Pet lovers": "I run an Etsy store specialized in pet lover products. Focus on emotional gifting, pet owners, dog lovers, cat lovers, practical use, cuteness and conversion-focused Etsy SEO.",
    "Beauté / Bien-être": "I run an Etsy store specialized in beauty and wellness products. Focus on self-care, routine, relaxation, gifting, premium feel and conversion-focused Etsy SEO.",
    "Mode générale": "I run an Etsy store specialized in fashion products. Focus on outfit ideas, style, comfort, seasonal trends, giftability and conversion-focused Etsy SEO.",
    "Prompt personnalisé": "Use the custom category context written by the user. Adapt the Etsy listing to that niche while keeping the output in English.",
}


def generate_listing(api_key: str, payload: Dict) -> Dict:
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": payload["prompt"]}],
        temperature=0.72,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def download_image(url: str) -> bytes | None:
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code == 200 and r.content:
            return r.content
    except Exception:
        return None
    return None


def make_square_preview(image_bytes: bytes) -> bytes | None:
    try:
        im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        im = ImageOps.exif_transpose(im)
        im = ImageOps.fit(im, (1200, 1200), method=Image.Resampling.LANCZOS, centering=(0.5, 0.45))
        im = ImageEnhance.Contrast(im).enhance(1.08)
        im = ImageEnhance.Sharpness(im).enhance(1.08)
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=92)
        return out.getvalue()
    except Exception:
        return None


def make_zip_from_images(urls: List[str], square: bool = False) -> bytes:
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, url in enumerate(urls, start=1):
            data = download_image(url)
            if not data:
                continue
            if square:
                data = make_square_preview(data) or data
                ext = "jpg"
            else:
                ext = "jpg"
            zf.writestr(f"etsy_image_{idx}.{ext}", data)
    mem.seek(0)
    return mem.getvalue()


def prepare_image_for_edit(image_bytes: bytes) -> io.BytesIO | None:
    """Convert the selected AliExpress image into a clean PNG file object for image editing."""
    try:
        im = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        im = ImageOps.exif_transpose(im)
        # Keep the full product visible, add white padding to square instead of cropping.
        im.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (1400, 1400), (255, 255, 255, 255))
        x = (1400 - im.width) // 2
        y = (1400 - im.height) // 2
        canvas.alpha_composite(im, (x, y))
        out = io.BytesIO()
        canvas.save(out, format="PNG")
        out.seek(0)
        out.name = "reference_product.png"
        return out
    except Exception:
        return None


def generate_ai_image_from_reference(api_key: str, photo_prompt: str, product_title: str, product_desc: str, reference_url: str) -> bytes | None:
    """Edit the selected AliExpress image as a visual reference instead of generating from text only.
    This gives much better product fidelity, but the user should still verify every image before Etsy upload.
    """
    original_bytes = download_image(reference_url)
    if not original_bytes:
        st.error("Impossible de télécharger l’image sélectionnée.")
        return None

    image_file = prepare_image_for_edit(original_bytes)
    if not image_file:
        st.error("Impossible de préparer l’image pour l’édition IA.")
        return None

    client = OpenAI(api_key=api_key)
    final_prompt = f"""Edit the provided reference product photo into an Etsy-ready luxury ecommerce image.

ABSOLUTE PRIORITY: preserve the exact product from the reference image.
- Keep the same garment/product design, shape, color, fabric, texture, embroidery, print, pattern, lace, seams, buttons, straps, closures, decorations and proportions.
- Do not replace the product with a different product.
- Do not invent new colors, flowers, patterns, accessories, or design details.
- If the reference image is a flat-lay product photo, keep the product visually identical and improve the presentation.
- If a model is added or changed, the product worn by the model must still match the reference product as closely as possible.

Product title/context: {product_title}
Product details/context: {product_desc[:1000]}

User image style instructions:
{photo_prompt}

Output requirements: square 1:1, ultra realistic, professional, luxury ecommerce style, no text, no logo, no watermark, Etsy-ready.
"""
    try:
        result = client.images.edit(
            model="gpt-image-1",
            image=image_file,
            prompt=final_prompt,
            size="1024x1024",
            n=1,
        )
        b64 = result.data[0].b64_json
        return base64.b64decode(b64)
    except Exception as e:
        st.error(f"Génération photo impossible : {e}")
        return None


DEFAULT_PHOTO_PROMPT = """You are a professional luxury ecommerce photographer and art director.

Your task is to recreate this product image while keeping the product 100% identical to the original.

Important requirements:
- The product itself must remain exactly the same.
- Do not modify the shape, color, texture, materials, details, patterns, accessories, or design of the product.
- Preserve all product features exactly as shown in the original image.
- Only improve the presentation and photography.

Photography style:
- Ultra realistic professional luxury fashion photography.
- Premium ecommerce quality.
- High-end boutique aesthetic.
- Clean and elegant composition.
- Natural studio lighting.
- Soft luxury shadows.
- High detail and sharp focus.
- Premium magazine-quality image.
- Expensive and sophisticated look.

Model requirements:
- Use a different professional-looking model if a model is needed.
- Attractive and natural appearance.
- Luxury fashion model style.
- Confident and elegant pose.
- Realistic skin and proportions.
- No exaggerated beauty filters.

Background requirements:
- Elegant luxury environment.
- High-end fashion editorial atmosphere.
- Minimalist premium decor.
- Neutral and sophisticated colors.
- Background must enhance the product without distracting from it.

Output requirements:
- Square format 1:1.
- Ultra realistic.
- High resolution.
- Etsy-ready product photography.
- Commercial ecommerce quality.
- No text.
- No watermark.
- No logo.
- No brand names.

Priority order:
1. Preserve the product exactly.
2. Improve image quality.
3. Create a luxury premium presentation.
4. Maximize conversion potential for Etsy buyers."""

# -------------------- STATE --------------------
if "product" not in st.session_state:
    st.session_state.product = {"title":"", "description":"", "price":"", "images":[]}
if "result" not in st.session_state:
    st.session_state.result = None
if "saved_prompts" not in st.session_state:
    st.session_state.saved_prompts = {}
if "generated_images" not in st.session_state:
    st.session_state.generated_images = []

OPENAI_SECRET = get_secret("OPENAI_API_KEY", "")
SCRAPER_SECRET = get_secret("SCRAPERAPI_KEY", "")

# -------------------- SIDEBAR --------------------
with st.sidebar:
    st.markdown("### 🔐 Clés")
    openai_key = st.text_input("Clé OpenAI", value=OPENAI_SECRET, type="password")
    scraper_key = st.text_input("Clé ScraperAPI", value=SCRAPER_SECRET, type="password")
    st.caption("Tu peux sauvegarder ces clés dans les Secrets Streamlit.")
    st.markdown("---")
    st.markdown("### 💰 Prix")
    margin = st.slider("Marge cible", 20, 90, 45)
    shipping = st.number_input("Livraison estimée", min_value=0.0, value=0.0, step=0.5)
    fees_pct = st.slider("Frais Etsy + paiement", 5, 30, 12)
    currency = st.selectbox("Devise", ["EUR", "USD", "GBP", "CAD", "AUD"], index=0)

# -------------------- HERO --------------------
st.markdown("""
<div class="hero">
  <h1>🛍️ Générateur Etsy SEO — Accueil unique</h1>
  <p style="font-size:18px;color:#4b5563;">Tout se fait sur cette page : lien AliExpress, prompts, photos, prix, génération et copie du résultat. L’interface est en français, mais les fiches Etsy sont générées en anglais pour le SEO.</p>
</div>
""", unsafe_allow_html=True)

# -------------------- MAIN LAYOUT --------------------
left, right = st.columns([1.08, 0.92], gap="large")

with left:
    st.markdown('<div class="card"><h3><span class="step-badge">1</span>Produit AliExpress</h3>', unsafe_allow_html=True)
    url = st.text_input("Lien AliExpress", placeholder="https://www.aliexpress.com/item/...")
    c1, c2 = st.columns([1,1])
    with c1:
        extract_clicked = st.button("🔎 Extraire infos + photos", use_container_width=True)
    with c2:
        if st.button("🧹 Vider le produit", use_container_width=True):
            st.session_state.product = {"title":"", "description":"", "price":"", "images":[]}
            st.session_state.generated_images = []
            st.rerun()
    if extract_clicked:
        if not url:
            st.warning("Colle un lien AliExpress d’abord.")
        else:
            with st.spinner("Extraction AliExpress en cours..."):
                html, err = fetch_url(url, scraper_key)
                if err or not html:
                    st.error(f"Extraction impossible : {err}. Colle les infos manuellement.")
                else:
                    data = extract_product_from_html(html)
                    st.session_state.product = data
                    if not data.get("title") and not data.get("description"):
                        st.warning("AliExpress a bloqué ou masqué les infos utiles. Tu peux coller le titre/description manuellement.")
                    else:
                        st.success("Infos extraites. Vérifie et modifie si besoin.")
                    st.rerun()

    product = st.session_state.product
    product["title"] = st.text_input("Titre fournisseur / AliExpress", value=product.get("title", ""), placeholder="Colle le titre du produit ici")
    product["description"] = st.text_area("Description fournisseur / AliExpress", value=product.get("description", ""), height=160, placeholder="Colle la description du produit ici")
    p1, p2 = st.columns(2)
    with p1:
        product["price"] = st.text_input("Prix fournisseur détecté", value=product.get("price", ""), placeholder="Optionnel")
    with p2:
        cost_price = st.number_input("Prix d’achat du produit", min_value=0.0, value=5.0, step=0.5)
    st.session_state.product = product
    sell_price = recommended_price(cost_price, shipping, margin, fees_pct)
    st.info(f"Prix conseillé estimé : **{sell_price} {currency}**")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><h3><span class="step-badge">2</span>SEO, catégorie et prompt</h3>', unsafe_allow_html=True)
    category = st.selectbox("Catégorie / type de boutique", list(CATEGORY_PRESETS.keys()))
    default_context = CATEGORY_PRESETS[category]
    category_context = st.text_area("Contexte de catégorie modifiable", value=default_context, height=95)
    niche = st.text_input("Client cible / niche", placeholder="Exemple : gothic fashion, gift for women, home decor")
    seo_keywords = st.text_input("Mots-clés SEO à ajouter", placeholder="Exemple : gothic corset, waist trainer, renaissance outfit")
    competitor = st.text_area("Fiche concurrente / inspiration", height=85, placeholder="Optionnel : colle ici une fiche concurrente. L’IA s’inspire mais ne copie pas.")
    tone = st.selectbox("Ton de rédaction", ["Premium and trustworthy", "Warm and emotional", "Minimalist and modern", "Gift-focused", "Luxury boutique"])
    main_prompt = st.text_area("Prompt principal modifiable", value=build_default_prompt(category_context), height=260)

    sp1, sp2, sp3 = st.columns([1,1,1])
    with sp1:
        prompt_name = st.text_input("Nom du prompt à sauvegarder", placeholder="Ex : Corsets luxe")
    with sp2:
        if st.button("💾 Sauvegarder prompt", use_container_width=True):
            if prompt_name:
                st.session_state.saved_prompts[prompt_name] = main_prompt
                st.success("Prompt sauvegardé pour cette session.")
            else:
                st.warning("Donne un nom au prompt.")
    with sp3:
        if st.session_state.saved_prompts:
            chosen = st.selectbox("Charger", list(st.session_state.saved_prompts.keys()))
            if st.button("📥 Utiliser", use_container_width=True):
                main_prompt = st.session_state.saved_prompts[chosen]
                st.rerun()

    if st.session_state.saved_prompts:
        st.download_button("⬇️ Télécharger mes prompts JSON", json.dumps(st.session_state.saved_prompts, ensure_ascii=False, indent=2), "prompts_etsy.json", "application/json")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><h3><span class="step-badge">3</span>Photos AliExpress et édition IA fidèle</h3>', unsafe_allow_html=True)
    images = st.session_state.product.get("images", []) or []
    if images:
        st.caption(f"{len(images)} image(s) trouvée(s). Sélectionne celles que tu veux garder ou transformer.")
        selected_urls = []
        cols = st.columns(4)
        for idx, img_url in enumerate(images[:12]):
            with cols[idx % 4]:
                st.image(img_url, use_container_width=True)
                if st.checkbox("Sélectionner", value=idx < 4, key=f"imgsel_{idx}"):
                    selected_urls.append(img_url)
        z1, z2 = st.columns(2)
        with z1:
            if selected_urls:
                st.download_button("⬇️ Télécharger photos originales", make_zip_from_images(selected_urls, square=False), "photos_aliexpress.zip", "application/zip", use_container_width=True)
        with z2:
            if selected_urls:
                st.download_button("⬇️ Télécharger photos carrées propres", make_zip_from_images(selected_urls, square=True), "photos_carrees_etsy.zip", "application/zip", use_container_width=True)
    else:
        selected_urls = []
        st.warning("Aucune photo extraite pour l’instant. Essaie avec ScraperAPI ou colle le titre/description manuellement.")

    photo_prompt = st.text_area(
        "Prompt photo personnalisable",
        value=DEFAULT_PHOTO_PROMPT,
        height=120,
    )
    col_img1, col_img2 = st.columns(2)
    with col_img1:
        nb_images = st.slider("Nombre de photos IA à générer depuis les images sélectionnées", 1, 4, 1)
    with col_img2:
        st.caption("Cette version utilise les photos sélectionnées comme référence visuelle. C’est beaucoup plus fidèle qu’une génération texte seule, mais vérifie toujours avant Etsy.")
    if st.button("✨ Générer nouvelles photos IA à partir des images sélectionnées", use_container_width=True):
        if not openai_key:
            st.error("Ajoute ta clé OpenAI d’abord.")
        elif not selected_urls:
            st.error("Sélectionne au moins une photo AliExpress à utiliser comme référence.")
        elif not product.get("title") and not product.get("description"):
            st.error("Ajoute ou extrais les infos produit avant de générer les photos.")
        else:
            st.session_state.generated_images = []
            urls_to_edit = selected_urls[:nb_images]
            with st.spinner("Génération des photos IA à partir des images sélectionnées..."):
                for ref_url in urls_to_edit:
                    img_data = generate_ai_image_from_reference(openai_key, photo_prompt, product.get("title",""), product.get("description",""), ref_url)
                    if img_data:
                        st.session_state.generated_images.append(img_data)
            if st.session_state.generated_images:
                st.success("Photos générées à partir des images sélectionnées. Vérifie bien que le produit est fidèle avant publication.")
                st.rerun()

    if st.session_state.generated_images:
        st.markdown("#### Photos IA générées")
        cols = st.columns(4)
        for i, data in enumerate(st.session_state.generated_images):
            with cols[i % 4]:
                st.image(data, use_container_width=True)
                st.download_button("Télécharger", data, f"photo_ia_{i+1}.png", "image/png", key=f"dl_ai_{i}")
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, data in enumerate(st.session_state.generated_images, start=1):
                zf.writestr(f"photo_ia_{i}.png", data)
        st.download_button("⬇️ Télécharger toutes les photos IA", mem.getvalue(), "photos_ia_etsy.zip", "application/zip", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

with right:
    st.markdown('<div class="card"><h3><span class="step-badge">4</span>Générer la fiche Etsy</h3>', unsafe_allow_html=True)
    final_prompt = f"""
{main_prompt}

Supplier title:
{product.get('title','')}

Supplier description:
{product.get('description','')}

Supplier price:
{product.get('price','')}

Target buyer / niche:
{niche}

Additional SEO keywords:
{seo_keywords}

Competitor / inspiration text, do not copy word-for-word:
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
    if st.button("🚀 Générer la fiche produit", use_container_width=True):
        if not openai_key:
            st.error("Ajoute ta clé OpenAI dans la colonne de gauche.")
        elif not product.get("title") and not product.get("description"):
            st.error("Ajoute ou extrais les infos produit d’abord.")
        else:
            with st.spinner("Génération SEO Etsy en anglais..."):
                try:
                    st.session_state.result = generate_listing(openai_key, {"prompt": final_prompt})
                    st.success("Fiche générée.")
                except Exception as e:
                    st.error(f"Génération impossible : {e}")
    st.markdown('</div>', unsafe_allow_html=True)

    result = st.session_state.result
    st.markdown('<div class="card"><h3>📋 Résultat prêt à copier</h3>', unsafe_allow_html=True)
    if not result:
        st.info("La fiche générée apparaîtra ici.")
    else:
        st.markdown("#### Titre SEO")
        st.code(result.get("seo_title", ""))
        st.markdown("#### Description courte")
        st.write(result.get("short_description", ""))
        st.markdown("#### Description complète")
        st.write(result.get("full_description", ""))
        st.markdown("#### Points clés")
        for b in result.get("bullet_points", []):
            st.write(f"• {b}")
        st.markdown("#### 13 tags Etsy")
        tags = result.get("tags", [])
        if isinstance(tags, list):
            tags_line = ", ".join(tags)
        else:
            tags_line = str(tags)
        st.code(tags_line)
        st.markdown("#### Prix conseillé")
        st.code(str(result.get("suggested_price", f"{sell_price} {currency}")))
        st.markdown("#### Bloc complet")
        st.text_area("Copie-colle dans Etsy", value=result.get("copy_paste_block", ""), height=300)
        st.download_button("⬇️ Télécharger la fiche TXT", result.get("copy_paste_block", ""), "fiche_etsy.txt", "text/plain", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="small-card">⚠️ Important : garde des photos fidèles au vrai produit et assure-toi d’avoir le droit d’utiliser les images. Évite les fiches trompeuses sur Etsy.</div>', unsafe_allow_html=True)
