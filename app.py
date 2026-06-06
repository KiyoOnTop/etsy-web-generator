import json
import re
import requests
from bs4 import BeautifulSoup
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Générateur Etsy SEO", page_icon="🛍️", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
/* ---------- Base lisible ---------- */
:root {
  --bg: #f6f7fb;
  --card: #ffffff;
  --card-soft: #f1f5f9;
  --text: #111827;
  --muted: #4b5563;
  --border: #d7dde8;
  --accent: #7c3aed;
  --accent-2: #ef4444;
}

html, body, [data-testid="stAppViewContainer"], .stApp {
  background: var(--bg) !important;
  color: var(--text) !important;
}

.block-container {
  padding-top: 1.4rem;
  padding-bottom: 2.5rem;
  max-width: 1180px;
}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
  background: #ffffff !important;
  border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] * {
  color: var(--text) !important;
}
[data-testid="stSidebar"] .stInfo {
  background: #e8f1ff !important;
  border: 1px solid #bfdbfe !important;
  border-radius: 12px !important;
}

/* ---------- Texte général ---------- */
h1, h2, h3, h4, h5, h6, p, span, label, div {
  color: var(--text) !important;
}
small, .caption, [data-testid="stCaptionContainer"], .step-help {
  color: var(--muted) !important;
}

/* ---------- Header ---------- */
.hero {
  padding: 1.7rem 1.8rem;
  border-radius: 22px;
  background: linear-gradient(135deg, #ffffff 0%, #f4f0ff 55%, #fff7ed 100%);
  border: 1px solid var(--border);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  margin-bottom: 1.1rem;
}
.hero h1 {
  margin: 0;
  font-size: 2.25rem;
  line-height: 1.1;
  color: #111827 !important;
}
.hero p {
  margin: .55rem 0 0 0;
  color: #374151 !important;
  font-size: 1.02rem;
}
.small-pill {
  display:inline-block;
  padding:.28rem .65rem;
  border-radius:999px;
  background:#ede9fe;
  color:#5b21b6 !important;
  font-weight:700;
  font-size:.82rem;
  margin-right:.35rem;
  margin-top:.25rem;
}

/* ---------- Onglets ---------- */
button[data-baseweb="tab"] {
  background: transparent !important;
  color: #111827 !important;
  font-weight: 800 !important;
}
button[data-baseweb="tab"] p {
  color: #111827 !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
  border-bottom: 3px solid var(--accent-2) !important;
}

/* ---------- Cartes ---------- */
.step-card, .result-card {
  padding: 1.15rem 1.2rem;
  border-radius: 18px;
  background: var(--card) !important;
  border: 1px solid var(--border);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.07);
  margin-bottom: 1rem;
}
.step-title, .copy-label {
  font-size: 1.05rem;
  font-weight: 800;
  margin-bottom: .3rem;
  color: #111827 !important;
}
.step-help {
  font-size: .95rem;
  margin-bottom: .65rem;
  line-height: 1.45;
}

/* ---------- Champs ---------- */
.stTextInput input,
.stTextArea textarea,
.stNumberInput input,
.stSelectbox div[data-baseweb="select"] > div {
  background: #ffffff !important;
  color: #111827 !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 12px !important;
}
.stTextInput input::placeholder,
.stTextArea textarea::placeholder {
  color: #6b7280 !important;
  opacity: 1 !important;
}
label, [data-testid="stWidgetLabel"] p {
  color: #111827 !important;
  font-weight: 700 !important;
}

/* ---------- Boutons ---------- */
.stButton>button {
  border-radius: 12px !important;
  font-weight: 800 !important;
  min-height: 2.6rem;
}
.stButton>button[kind="primary"] {
  background: #ef4444 !important;
  color: #ffffff !important;
  border: 1px solid #ef4444 !important;
}
.stButton>button:not([kind="primary"]) {
  background: #ffffff !important;
  color: #111827 !important;
  border: 1px solid #cbd5e1 !important;
}

/* ---------- Alerts / métriques ---------- */
[data-testid="stMetricValue"] {
  font-size: 1.45rem !important;
  color: #111827 !important;
}
[data-testid="stMetricLabel"] p {
  color: #374151 !important;
}
.stAlert {
  border-radius: 12px !important;
  color: #111827 !important;
}
hr {margin: 1rem 0; border-color: var(--border);}

/* ---------- Code / zones copier ---------- */
pre, code {
  color: #111827 !important;
  background: #f8fafc !important;
}

/* Enlève l'effet trop sombre de certains thèmes Streamlit */
[data-baseweb="input"], [data-baseweb="textarea"] {
  background: transparent !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <h1>🛍️ Générateur Etsy SEO</h1>
  <p>Interface simple en français. Le contenu Etsy généré reste en anglais pour maximiser le SEO et la conversion.</p>
  <div style="margin-top:.8rem;">
    <span class="small-pill">URL AliExpress</span>
    <span class="small-pill">Prompt modifiable</span>
    <span class="small-pill">Catégories</span>
    <span class="small-pill">Tags Etsy</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ---------- Helpers ----------
def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

OPENAI_SECRET = get_secret("OPENAI_API_KEY", "")
SCRAPERAPI_SECRET = get_secret("SCRAPERAPI_KEY", "")

CATEGORY_PROMPTS = {
    "Corsets / Lingerie / Mode alternative": """I run an Etsy store specialized in corsets, lingerie-inspired fashion, gothic fashion, renaissance fashion, burlesque fashion, shapewear and alternative fashion. Focus on style, confidence, giftability, comfort, outfit ideas and conversion-focused Etsy SEO.""",
    "Bijoux / Accessoires": """I run an Etsy store specialized in jewelry and fashion accessories. Focus on giftable wording, elegant style, daily wear, special occasions, aesthetic keywords and conversion-focused Etsy SEO.""",
    "Décoration maison": """I run an Etsy store specialized in home decor. Focus on cozy home styling, aesthetic interiors, gift ideas, room decoration, modern decor keywords and conversion-focused Etsy SEO.""",
    "Animaux / Accessoires pet": """I run an Etsy store specialized in pet accessories. Focus on pet lovers, useful features, cute design, gift ideas for pet owners and conversion-focused Etsy SEO.""",
    "Beauté / Bien-être": """I run an Etsy store specialized in beauty and wellness products. Focus on self-care, routine, giftability, aesthetic presentation and conversion-focused Etsy SEO. Avoid medical claims.""",
    "Mode femme": """I run an Etsy store specialized in women's fashion. Focus on outfit ideas, flattering style, seasonal trends, giftability and conversion-focused Etsy SEO.""",
    "Catégorie personnalisée": """I run an Etsy store. Adapt the listing to the product category and target buyer provided by the user. Focus on natural English, strong Etsy SEO, conversion and buyer trust.""",
}

DEFAULT_PROMPT = """You are an Etsy SEO expert and high-converting product listing copywriter.

Your mission is to generate a complete Etsy product listing from supplier data.

The final listing must be written in English only.

Generate:
1. One SEO-optimized Etsy title, clearly related to the product keywords, natural and effective for search.
2. A warm, fluent, persuasive SEO product description in English with a few relevant emojis, but not too many.
3. Exactly 13 Etsy tags, each maximum 20 characters if possible, on one single line separated by commas.

Important rules:
- Do NOT claim handmade unless explicitly stated.
- Do NOT copy competitor text word-for-word.
- Avoid keyword stuffing.
- Keep the title under 140 characters.
- Keep the tone natural, trustworthy and conversion-focused.
- Use the strongest Etsy search keywords naturally in the title and first paragraph.
- Tags must be practical Etsy tags, not random words.
- Output valid JSON only.
"""

with st.sidebar:
    st.markdown("### ⚙️ Réglages")
    openai_key = st.text_input("Clé API OpenAI", value=OPENAI_SECRET, type="password", help="Obligatoire pour générer les fiches produits.")
    scraperapi_key = st.text_input("Clé ScraperAPI", value=SCRAPERAPI_SECRET, type="password", help="Optionnel, mais recommandé pour lire AliExpress.")
    st.info("Astuce : sauvegarde tes clés dans les Secrets Streamlit pour ne plus les retaper.")
    st.markdown("---")
    st.markdown("### 💰 Prix")
    margin = st.slider("Marge cible", 20, 90, 45, format="%d%%")
    shipping = st.number_input("Livraison estimée", min_value=0.0, value=0.0, step=0.5)
    fees_pct = st.slider("Frais Etsy + paiement", 5, 30, 12, format="%d%%")
    currency = st.selectbox("Devise", ["USD", "EUR", "GBP", "CAD", "AUD"], index=1)


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:8000]


def fetch_url(url: str, scraper_key: str = ""):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    }
    try:
        if scraper_key:
            api_url = "http://api.scraperapi.com/"
            r = requests.get(api_url, params={"api_key": scraper_key, "url": url, "render": "true", "country_code": "us", "premium": "true"}, timeout=60)
        else:
            r = requests.get(url, headers=headers, timeout=25)
        if r.status_code >= 400:
            return None, f"Erreur HTTP {r.status_code}"
        return r.text, None
    except Exception as e:
        return None, str(e)


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

    meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    if meta_desc and meta_desc.get("content"):
        desc_parts.append(meta_desc["content"])

    text = html
    candidates = re.findall(r'"(?:subject|title|productTitle)"\s*:\s*"(.*?)"', text)
    if candidates:
        title = max([c.encode("utf-8").decode("unicode_escape", errors="ignore") for c in candidates], key=len)
    desc_candidates = re.findall(r'"(?:description|productDescription|seoDescription)"\s*:\s*"(.*?)"', text)
    for c in desc_candidates[:5]:
        desc_parts.append(c.encode("utf-8").decode("unicode_escape", errors="ignore"))
    price_candidates = re.findall(r'"(?:salePrice|formattedPrice|price)"\s*:\s*"?([^",}]+)', text)
    if price_candidates:
        price = price_candidates[0]

    title = clean_text(title.replace("| AliExpress", "").replace("- AliExpress", ""))
    description = clean_text("\n".join(desc_parts))
    return {"title": title, "description": description, "price": clean_text(price)}


def recommended_price(cost, shipping_cost, margin_pct, fees_percentage):
    denominator = 1 - (margin_pct / 100) - (fees_percentage / 100)
    if denominator <= 0.05:
        denominator = 0.05
    return round((cost + shipping_cost) / denominator, 2)


def generate_listing(api_key, data, niche, tone, cost_price, base_prompt, category_context, seo_keywords, competitor_text):
    client = OpenAI(api_key=api_key)
    sell_price = recommended_price(cost_price, shipping, margin, fees_pct)
    prompt = f"""
{base_prompt}

Store/category context:
{category_context}

Supplier title:
{data.get('title','')}

Supplier description:
{data.get('description','')}

Supplier price:
{data.get('price','')}

Target buyer / niche:
{niche}

Extra SEO keywords to consider:
{seo_keywords}

Competitor listing or inspiration text. Use only for inspiration, never copy word-for-word:
{competitor_text}

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

# ---------- UI ----------
extracted = st.session_state.get("extracted", {"title": "", "description": "", "price": ""})

tab1, tab2, tab3 = st.tabs(["1️⃣ Produit", "2️⃣ SEO & Prompt", "3️⃣ Résultat"])

with tab1:
    st.markdown('<div class="step-card"><div class="step-title">📦 Étape 1 — Récupère ou colle les infos produit</div><div class="step-help">Colle un lien AliExpress puis essaie l’extraction. Si AliExpress bloque, colle le titre et la description manuellement.</div>', unsafe_allow_html=True)
    url = st.text_input("Lien AliExpress", placeholder="https://www.aliexpress.com/item/...")
    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1:
        extract_clicked = st.button("🔎 Extraire depuis AliExpress", type="primary", use_container_width=True)
    with c2:
        if st.button("🧹 Vider le produit", use_container_width=True):
            st.session_state["extracted"] = {"title": "", "description": "", "price": ""}
            st.session_state.pop("result", None)
            st.rerun()
    with c3:
        st.caption("ScraperAPI recommandé si AliExpress bloque.")

    if extract_clicked:
        if not url:
            st.warning("Colle d'abord un lien AliExpress.")
        else:
            with st.spinner("Lecture de la page produit..."):
                html, err = fetch_url(url, scraperapi_key)
                if err or not html:
                    st.error(f"Extraction impossible : {err}. Colle les informations du produit manuellement plus bas.")
                else:
                    data = extract_product_from_html(html)
                    if not data.get("title") and not data.get("description"):
                        st.warning("AliExpress a bloqué ou caché les données utiles. Ajoute une clé ScraperAPI ou colle les infos manuellement.")
                    else:
                        st.session_state["extracted"] = data
                        st.success("Informations extraites. Tu peux les vérifier ou les modifier ci-dessous.")
                        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    colp1, colp2 = st.columns([1.2, .8])
    with colp1:
        title = st.text_input("Titre fournisseur / AliExpress", value=extracted.get("title", ""), placeholder="Colle le titre du produit ici")
        description = st.text_area("Description fournisseur / AliExpress", value=extracted.get("description", ""), height=230, placeholder="Colle la description AliExpress ici")
    with colp2:
        supplier_price = st.text_input("Prix fournisseur détecté", value=extracted.get("price", ""), placeholder="Optionnel")
        cost_price = st.number_input("Prix d'achat du produit", min_value=0.0, value=5.0, step=0.5)
        estimated = recommended_price(cost_price, shipping, margin, fees_pct)
        st.metric("Prix conseillé estimé", f"{estimated} {currency}")
        st.caption("Ce prix est recalculé avec ta marge, tes frais Etsy et la livraison estimée.")

with tab2:
    st.markdown('<div class="step-card"><div class="step-title">🎯 Étape 2 — Choisis la stratégie SEO</div><div class="step-help">Tu peux utiliser une catégorie prête à l’emploi ou modifier le prompt selon ta niche.</div>', unsafe_allow_html=True)
    sc1, sc2 = st.columns([.9, 1.1])
    with sc1:
        selected_category = st.selectbox("Catégorie / type de boutique", list(CATEGORY_PROMPTS.keys()))
        niche = st.text_input("Client cible / niche", placeholder="Exemple : gothic fashion, gift for women, home decor")
        seo_keywords = st.text_input("Mots-clés SEO à ajouter", placeholder="Exemple : gothic corset, waist trainer, renaissance outfit")
        tone = st.selectbox("Ton de rédaction", ["Premium and trustworthy", "Warm and emotional", "Minimalist and modern", "Gift-focused", "Luxury boutique"])
    with sc2:
        category_context = st.text_area("Contexte de catégorie modifiable", value=CATEGORY_PROMPTS[selected_category], height=150)
        competitor_text = st.text_area("Fiche concurrente / inspiration", height=120, placeholder="Optionnel : colle ici un titre ou une description concurrente. L’IA ne doit pas copier.")
    st.markdown('</div>', unsafe_allow_html=True)

    with st.expander("🧠 Modifier le prompt principal", expanded=False):
        st.caption("À modifier seulement si tu veux changer la logique globale. Les réponses Etsy resteront en anglais.")
        if st.button("Réinitialiser le prompt par défaut"):
            st.session_state["base_prompt"] = DEFAULT_PROMPT
            st.rerun()
        base_prompt = st.text_area("Prompt principal", value=st.session_state.get("base_prompt", DEFAULT_PROMPT), height=280)
        st.session_state["base_prompt"] = base_prompt

    st.markdown("---")
    gen_col1, gen_col2 = st.columns([1, 1])
    with gen_col1:
        generate_clicked = st.button("✨ Générer la fiche Etsy en anglais", type="primary", use_container_width=True)
    with gen_col2:
        st.caption("Après génération, va dans l’onglet Résultat pour copier le titre, la description et les tags.")

    if generate_clicked:
        if not openai_key:
            st.error("Ajoute ta clé API OpenAI dans la barre de gauche.")
        elif not title and not description:
            st.error("Va dans l’onglet Produit et colle au minimum un titre ou une description.")
        else:
            with st.spinner("Génération de la fiche Etsy en anglais..."):
                try:
                    result = generate_listing(openai_key, {"title": title, "description": description, "price": supplier_price}, niche, tone, cost_price, st.session_state.get("base_prompt", DEFAULT_PROMPT), category_context, seo_keywords, competitor_text)
                    st.session_state["result"] = result
                    st.success("Fiche générée ! Ouvre l’onglet Résultat.")
                except Exception as e:
                    st.error(f"La génération a échoué : {e}")

with tab3:
    result = st.session_state.get("result")
    st.markdown('<div class="step-card"><div class="step-title">✅ Étape 3 — Copie ta fiche dans Etsy</div><div class="step-help">Les blocs ci-dessous sont prêts à copier-coller dans ta fiche Etsy.</div></div>', unsafe_allow_html=True)
    if not result:
        st.info("Aucune fiche générée pour le moment. Va dans l’onglet Produit puis SEO & Prompt.")
    else:
        tags = result.get("tags", [])
        tags_line = ", ".join(tags) if isinstance(tags, list) else str(tags)
        keywords = result.get("keywords", [])
        keywords_line = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)

        r1, r2 = st.columns([1.05, .95])
        with r1:
            st.markdown('<div class="result-card"><div class="copy-label">Titre SEO Etsy</div>', unsafe_allow_html=True)
            st.text_area("Titre", value=result.get("seo_title", ""), height=85, label_visibility="collapsed")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="result-card"><div class="copy-label">Description complète</div>', unsafe_allow_html=True)
            st.text_area("Description", value=result.get("full_description", ""), height=260, label_visibility="collapsed")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="result-card"><div class="copy-label">Bloc complet prêt à copier</div>', unsafe_allow_html=True)
            st.text_area("Bloc complet", value=result.get("copy_paste_block", ""), height=300, label_visibility="collapsed")
            st.markdown('</div>', unsafe_allow_html=True)
        with r2:
            st.markdown('<div class="result-card"><div class="copy-label">Description courte</div>', unsafe_allow_html=True)
            st.write(result.get("short_description", ""))
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="result-card"><div class="copy-label">13 tags Etsy</div>', unsafe_allow_html=True)
            st.text_area("Tags", value=tags_line, height=95, label_visibility="collapsed")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="result-card"><div class="copy-label">Points clés</div>', unsafe_allow_html=True)
            for b in result.get("bullet_points", []):
                st.write(f"• {b}")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="result-card"><div class="copy-label">SEO & prix</div>', unsafe_allow_html=True)
            st.write("**Catégorie suggérée :**", result.get("category_suggestion", ""))
            st.write("**Mots-clés :**", keywords_line)
            st.write("**Prix conseillé :**", result.get("suggested_price", ""))
            st.markdown('</div>', unsafe_allow_html=True)
