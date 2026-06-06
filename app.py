import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Générateur Etsy SEO V12", page_icon="🛍️", layout="wide")

# ---------------- STYLE ----------------
st.markdown("""
<style>
:root { --primary:#ff4b4b; --soft:#fff5f5; --border:#e5e7eb; --text:#111827; }
.stApp { background:#f7f8fb; color:var(--text); }
.block-container { padding-top:2rem; max-width:1200px; }
.main-card { background:white; border:1px solid var(--border); border-radius:20px; padding:28px; box-shadow:0 10px 30px rgba(0,0,0,.05); margin-bottom:18px; }
.hero { background:linear-gradient(135deg,#ffffff,#fff1f1); border:1px solid #f1d4d4; border-radius:24px; padding:30px; margin-bottom:24px; }
.hero h1 { margin:0; font-size:34px; }
.hero p { color:#4b5563; font-size:16px; }
.badge { display:inline-block; background:#ffe7e7; color:#b91c1c; padding:7px 12px; border-radius:999px; font-weight:700; font-size:13px; margin-right:8px; }
.helpbox { background:#eff6ff; border:1px solid #bfdbfe; border-radius:14px; padding:15px; color:#1e3a8a; }
.warnbox { background:#fff7ed; border:1px solid #fed7aa; border-radius:14px; padding:15px; color:#9a3412; }
.successbox { background:#ecfdf5; border:1px solid #a7f3d0; border-radius:14px; padding:15px; color:#065f46; }
.big-result { background:white; border:1px solid var(--border); border-radius:16px; padding:18px; margin:10px 0; }
.small-muted { color:#6b7280; font-size:14px; }

/* Corrections lisibilité Streamlit */
.stTabs [data-baseweb="tab-list"] { gap: 10px; border-bottom: 1px solid #d1d5db; }
.stTabs [data-baseweb="tab"] {
    background: #ffffff !important;
    border: 1px solid #d1d5db !important;
    border-radius: 12px 12px 0 0 !important;
    padding: 10px 16px !important;
    color: #111827 !important;
    font-weight: 700 !important;
}
.stTabs [data-baseweb="tab"] p,
.stTabs [data-baseweb="tab"] span,
.stTabs [data-baseweb="tab"] div {
    color: #111827 !important;
    font-weight: 700 !important;
}
.stTabs [aria-selected="true"] {
    background: #fff1f1 !important;
    border-bottom: 3px solid #ff4b4b !important;
}
label, .stMarkdown, .stText, p, span, div { color: #111827; }
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div {
    color: #111827 !important;
}
[data-testid="stSidebar"] {
    background: #ffffff !important;
}

</style>
""", unsafe_allow_html=True)

# ---------------- HELPERS ----------------
def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

OPENAI_SECRET = get_secret("OPENAI_API_KEY", "")
SCRAPERAPI_SECRET = get_secret("SCRAPERAPI_KEY", "")

DEFAULT_CORSET_PROMPT = """I run an Etsy store specialized in corsets, lingerie-inspired fashion, gothic fashion, renaissance fashion, burlesque fashion, shapewear and alternative fashion.

Your mission is to generate a complete Etsy product listing in English.

Rules:
- Create a natural SEO Etsy title, under 140 characters.
- Write a warm, persuasive and fluent English description.
- Add a few relevant emojis, but not too many.
- Generate exactly 13 Etsy tags.
- Each Etsy tag must be maximum 20 characters.
- Tags must be on one single line, separated by commas.
- Do not claim handmade unless explicitly stated.
- Do not copy competitors word-for-word.
- Avoid keyword stuffing.
- Keep the style premium, trustworthy and conversion-focused.
- Use the strongest Etsy keywords naturally in the title and first paragraph.
"""

CATEGORY_PROMPTS = {
    "Corsets / Lingerie / Mode alternative": DEFAULT_CORSET_PROMPT,
    "Bijoux / Accessoires": """I run an Etsy store specialized in jewelry, accessories and giftable fashion items.
Generate an English Etsy listing with a premium, gift-focused and natural tone. Create exactly 13 Etsy tags, each max 20 characters, on one single comma-separated line. Avoid keyword stuffing and never copy competitors.""",
    "Décoration maison": """I run an Etsy store specialized in home decor and aesthetic room accessories.
Generate an English Etsy listing focused on home styling, gift ideas and visual appeal. Create exactly 13 Etsy tags, each max 20 characters, on one single comma-separated line. Avoid keyword stuffing and never copy competitors.""",
    "Animaux / Pet lovers": """I run an Etsy store specialized in pet lovers products and animal-themed gifts.
Generate an English Etsy listing with a warm, emotional and giftable tone. Create exactly 13 Etsy tags, each max 20 characters, on one single comma-separated line. Avoid keyword stuffing and never copy competitors.""",
    "Beauté / Bien-être": """I run an Etsy store specialized in beauty, self-care and wellness-inspired products.
Generate an English Etsy listing with a clean, premium and trustworthy tone. Create exactly 13 Etsy tags, each max 20 characters, on one single comma-separated line. Avoid medical claims, keyword stuffing and competitor copying.""",
    "Mode générale": """I run an Etsy store specialized in fashion items and accessories.
Generate an English Etsy listing focused on style, outfit ideas, giftability and conversion. Create exactly 13 Etsy tags, each max 20 characters, on one single comma-separated line. Avoid keyword stuffing and never copy competitors.""",
    "Prompt personnalisé": ""
}


def clean_text(text: str, limit: int = 8000) -> str:
    text = text or ""
    text = re.sub(r"\\u003c", "<", text)
    text = re.sub(r"\\u003e", ">", text)
    text = re.sub(r"\\/", "/", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def is_valid_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def fetch_url_fast(url: str, scraper_key: str = ""):
    """Fast extraction: no JS rendering by default, because render=true often times out on AliExpress."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    }
    try:
        if scraper_key:
            r = requests.get(
                "https://api.scraperapi.com/",
                params={
                    "api_key": scraper_key,
                    "url": url,
                    "country_code": "us",
                    "premium": "false",
                },
                timeout=35,
            )
        else:
            r = requests.get(url, headers=headers, timeout=18)
        if r.status_code >= 400:
            return None, f"Erreur HTTP {r.status_code}"
        return r.text, None
    except requests.exceptions.Timeout:
        return None, "AliExpress ou ScraperAPI met trop longtemps à répondre. Réessaie ou colle les infos manuellement."
    except Exception as e:
        return None, str(e)


def extract_product_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    desc_parts = []
    price = ""

    # basic meta
    if soup.title and soup.title.string:
        title = soup.title.string
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title.get("content")
    meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    if meta_desc and meta_desc.get("content"):
        desc_parts.append(meta_desc.get("content"))

    text = html

    # AliExpress JSON fields
    title_patterns = [
        r'"subject"\s*:\s*"(.*?)"',
        r'"title"\s*:\s*"(.*?)"',
        r'"productTitle"\s*:\s*"(.*?)"',
        r'"seoTitle"\s*:\s*"(.*?)"',
    ]
    titles = []
    for pat in title_patterns:
        titles += re.findall(pat, text)
    if titles:
        decoded = []
        for c in titles:
            try:
                decoded.append(bytes(c, "utf-8").decode("unicode_escape"))
            except Exception:
                decoded.append(c)
        title = max(decoded, key=len)

    desc_patterns = [
        r'"description"\s*:\s*"(.*?)"',
        r'"productDescription"\s*:\s*"(.*?)"',
        r'"seoDescription"\s*:\s*"(.*?)"',
    ]
    for pat in desc_patterns:
        for c in re.findall(pat, text)[:5]:
            try:
                desc_parts.append(bytes(c, "utf-8").decode("unicode_escape"))
            except Exception:
                desc_parts.append(c)

    price_patterns = [
        r'"salePrice"\s*:\s*"?([^",}]+)',
        r'"formattedPrice"\s*:\s*"?([^",}]+)',
        r'"price"\s*:\s*"?([^",}]+)',
    ]
    for pat in price_patterns:
        m = re.findall(pat, text)
        if m:
            price = m[0]
            break

    title = clean_text(title.replace("| AliExpress", "").replace("- AliExpress", ""), 500)
    description = clean_text("\n".join(desc_parts), 4000)
    price = clean_text(price, 100)
    return {"title": title, "description": description, "price": price}


def recommended_price(cost, shipping, margin_pct, fees_pct):
    denominator = 1 - (margin_pct / 100) - (fees_pct / 100)
    if denominator <= 0.05:
        denominator = 0.05
    return round((cost + shipping) / denominator, 2)


def generate_listing(api_key, data, niche, tone, cost_price, currency, shipping, margin, fees_pct, category_prompt, seo_keywords, competitor_text):
    client = OpenAI(api_key=api_key)
    sell_price = recommended_price(cost_price, shipping, margin, fees_pct)

    prompt = f"""
You are an Etsy SEO expert and high-converting product listing copywriter.

IMPORTANT: The final Etsy listing must be written in ENGLISH only.
The user interface is French, but all generated product content must be English.

CATEGORY / STORE STRATEGY PROMPT:
{category_prompt}

SUPPLIER DATA:
Supplier title: {data.get('title','')}
Supplier description: {data.get('description','')}
Supplier price: {data.get('price','')}

USER SEO INPUT:
Target buyer / niche: {niche}
Additional SEO keywords to include naturally: {seo_keywords}
Competitor or inspiration text, do not copy word-for-word: {competitor_text}
Tone: {tone}

PRICING:
Cost price: {cost_price} {currency}
Suggested selling price: {sell_price} {currency}

OUTPUT RULES:
- Return valid JSON only.
- seo_title must be under 140 characters.
- tags must contain exactly 13 tags.
- each tag should be max 20 characters when possible.
- tags must be useful Etsy search phrases, not random words.
- copy_paste_block must include title, description, tags, keywords and suggested price.

JSON keys:
seo_title, short_description, full_description, bullet_points, tags, keywords, category_suggestion, suggested_price, copy_paste_block
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.header("⚙️ Réglages")
    openai_key = st.text_input("Clé OpenAI", value=OPENAI_SECRET, type="password")
    scraperapi_key = st.text_input("Clé ScraperAPI", value=SCRAPERAPI_SECRET, type="password")
    st.markdown('<div class="helpbox">Astuce : mets tes clés dans les Secrets Streamlit pour ne plus les retaper.</div>', unsafe_allow_html=True)
    st.divider()
    st.subheader("💰 Prix")
    margin = st.slider("Marge cible", 20, 90, 45)
    shipping = st.number_input("Livraison estimée", min_value=0.0, value=0.0, step=0.5)
    fees_pct = st.slider("Frais Etsy + paiement", 5, 30, 12)
    currency = st.selectbox("Devise", ["EUR", "USD", "GBP", "CAD", "AUD"], index=0)

# ---------------- HEADER ----------------
st.markdown("""
<div class="hero">
  <h1>🛍️ Générateur Etsy SEO V12</h1>
  <p>Interface en français. Les titres, descriptions et tags Etsy sont générés en anglais pour le SEO.</p>
  <span class="badge">Extraction rapide</span><span class="badge">Prompts sauvegardables</span><span class="badge">Sans photos</span>
</div>
""", unsafe_allow_html=True)

tab_product, tab_seo, tab_result = st.tabs(["1️⃣ Produit", "2️⃣ SEO & Prompt", "3️⃣ Résultat"])

# session defaults
if "extracted" not in st.session_state:
    st.session_state.extracted = {"title": "", "description": "", "price": ""}
if "saved_prompts" not in st.session_state:
    st.session_state.saved_prompts = {}

with tab_product:
    st.markdown('<div class="main-card">', unsafe_allow_html=True)
    st.subheader("📦 Étape 1 — Récupère ou colle les infos produit")
    st.write("Colle un lien AliExpress puis essaie l'extraction. Si AliExpress bloque, colle le titre et la description manuellement.")

    url = st.text_input("Lien AliExpress", placeholder="https://www.aliexpress.com/item/...")
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("🔎 Extraire depuis AliExpress", type="primary", use_container_width=True):
            if not url or not is_valid_url(url):
                st.warning("Colle d'abord un lien AliExpress valide.")
            else:
                with st.spinner("Extraction rapide en cours..."):
                    html, err = fetch_url_fast(url, scraperapi_key)
                    if err or not html:
                        st.error(f"Extraction impossible : {err}")
                        st.info("Solution : réessaie une fois, ou colle le titre et la description manuellement.")
                    else:
                        data = extract_product_from_html(html)
                        if not data.get("title") and not data.get("description"):
                            st.warning("AliExpress cache les infos utiles. Colle le titre et la description manuellement.")
                        else:
                            st.session_state.extracted = data
                            st.success("Infos récupérées. Vérifie et complète si besoin.")
                            st.rerun()
    with c2:
        if st.button("🧹 Vider le produit", use_container_width=True):
            st.session_state.extracted = {"title": "", "description": "", "price": ""}
            st.rerun()

    extracted = st.session_state.extracted
    title = st.text_input("Titre fournisseur / AliExpress", value=extracted.get("title", ""), placeholder="Colle le titre du produit ici")
    description = st.text_area("Description fournisseur / AliExpress", value=extracted.get("description", ""), height=220, placeholder="Colle la description AliExpress ici")
    colp1, colp2 = st.columns(2)
    with colp1:
        supplier_price = st.text_input("Prix fournisseur détecté", value=extracted.get("price", ""), placeholder="Optionnel")
    with colp2:
        cost_price = st.number_input("Prix d'achat du produit", min_value=0.0, value=5.0, step=0.5)
    est = recommended_price(cost_price, shipping, margin, fees_pct)
    st.markdown(f'<div class="successbox"><b>Prix conseillé estimé :</b> {est} {currency}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with tab_seo:
    st.markdown('<div class="main-card">', unsafe_allow_html=True)
    st.subheader("🎯 Étape 2 — Choisis ou modifie ta stratégie SEO")

    category = st.selectbox("Catégorie / type de boutique", list(CATEGORY_PROMPTS.keys()))
    default_prompt = CATEGORY_PROMPTS.get(category, DEFAULT_CORSET_PROMPT)

    if "current_prompt" not in st.session_state or st.session_state.get("last_category") != category:
        st.session_state.current_prompt = default_prompt
        st.session_state.last_category = category

    niche = st.text_input("Client cible / niche", placeholder="Exemple : gothic fashion, gift for women, home decor")
    seo_keywords = st.text_input("Mots-clés SEO à ajouter", placeholder="Exemple : gothic corset, waist trainer, renaissance outfit")
    competitor_text = st.text_area("Fiche concurrente / inspiration", height=100, placeholder="Optionnel : colle ici un titre ou une description concurrente. L'IA ne doit pas copier.")
    tone = st.selectbox("Ton de rédaction", ["Premium and trustworthy", "Warm and emotional", "Minimalist and modern", "Gift-focused", "Luxury boutique"])

    st.markdown("### Prompt principal modifiable")
    st.session_state.current_prompt = st.text_area("Tu peux modifier ce prompt avant de générer", value=st.session_state.current_prompt, height=260)

    save_name = st.text_input("Nom pour sauvegarder ce prompt", placeholder="Exemple : Corsets luxe, Bijoux cadeaux, Déco maison")
    a, b, c = st.columns(3)
    with a:
        if st.button("💾 Sauvegarder ce prompt", use_container_width=True):
            if save_name.strip():
                st.session_state.saved_prompts[save_name.strip()] = st.session_state.current_prompt
                st.success("Prompt sauvegardé pour cette session.")
            else:
                st.warning("Ajoute un nom avant de sauvegarder.")
    with b:
        if st.button("↩️ Remettre le prompt catégorie", use_container_width=True):
            st.session_state.current_prompt = default_prompt
            st.rerun()
    with c:
        prompts_json = json.dumps(st.session_state.saved_prompts, ensure_ascii=False, indent=2)
        st.download_button("⬇️ Télécharger prompts", data=prompts_json, file_name="mes_prompts_etsy.json", mime="application/json", use_container_width=True)

    if st.session_state.saved_prompts:
        chosen_saved = st.selectbox("Charger un prompt sauvegardé", [""] + list(st.session_state.saved_prompts.keys()))
        if chosen_saved and st.button("Charger ce prompt"):
            st.session_state.current_prompt = st.session_state.saved_prompts[chosen_saved]
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

with tab_result:
    st.markdown('<div class="main-card">', unsafe_allow_html=True)
    st.subheader("🚀 Étape 3 — Générer la fiche Etsy")
    st.write("Le résultat sera en anglais : titre SEO, description, tags, prix et bloc prêt à copier-coller.")

    if st.button("✨ Générer la fiche Etsy", type="primary", use_container_width=True):
        if not openai_key:
            st.error("Ajoute ta clé OpenAI dans la barre de gauche.")
        elif not title and not description:
            st.error("Ajoute d'abord un titre ou une description produit.")
        else:
            with st.spinner("Génération de la fiche Etsy en anglais..."):
                try:
                    result = generate_listing(
                        openai_key,
                        {"title": title, "description": description, "price": supplier_price},
                        niche,
                        tone,
                        cost_price,
                        currency,
                        shipping,
                        margin,
                        fees_pct,
                        st.session_state.current_prompt,
                        seo_keywords,
                        competitor_text,
                    )
                    st.session_state.result = result
                    st.success("Fiche générée.")
                except Exception as e:
                    st.error(f"Génération impossible : {e}")

    result = st.session_state.get("result")
    if not result:
        st.info("Ta fiche générée apparaîtra ici.")
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
        st.markdown("### Suggested price")
        st.code(str(result.get("suggested_price", "")), language=None)
        st.markdown("### Bloc prêt à copier-coller")
        st.text_area("Ready to copy", value=result.get("copy_paste_block", ""), height=320)
    st.markdown('</div>', unsafe_allow_html=True)
