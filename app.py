import json
import re
import requests
from bs4 import BeautifulSoup
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Générateur Etsy SEO", page_icon="🛍️", layout="wide")

st.title("🛍️ Générateur de fiches produits Etsy")
st.caption("Interface en français. Les titres, descriptions et tags générés sont en anglais pour optimiser le SEO Etsy.")

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
    st.header("⚙️ Réglages")
    openai_key = st.text_input("Clé API OpenAI", value=OPENAI_SECRET, type="password", help="Obligatoire pour générer les fiches produits.")
    scraperapi_key = st.text_input("Clé ScraperAPI optionnelle", value=SCRAPERAPI_SECRET, type="password", help="Aide à lire AliExpress quand le site bloque l'extraction.")
    st.caption("Les clés peuvent être sauvegardées dans les Secrets Streamlit pour éviter de les retaper.")
    st.divider()
    margin = st.slider("Marge cible en %", 20, 90, 45)
    shipping = st.number_input("Coût de livraison estimé", min_value=0.0, value=0.0, step=0.5)
    fees_pct = st.slider("Frais Etsy + paiement estimés en %", 5, 30, 12)
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
            r = requests.get(
                api_url,
                params={
                    "api_key": scraper_key,
                    "url": url,
                    "render": "true",
                    "country_code": "us",
                    "premium": "true",
                },
                timeout=60,
            )
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
left, right = st.columns([1.05, 0.95])

with left:
    st.subheader("📦 Source produit")
    url = st.text_input("Lien AliExpress du produit")

    colA, colB = st.columns(2)
    extracted = st.session_state.get("extracted", {"title": "", "description": "", "price": ""})

    with colA:
        if st.button("Extraire depuis le lien AliExpress", type="primary"):
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
                            st.success("Informations produit extraites. Vérifie ou modifie les champs ci-dessous.")
                            st.rerun()

    with colB:
        if st.button("Vider les champs"):
            st.session_state["extracted"] = {"title": "", "description": "", "price": ""}
            st.session_state.pop("result", None)
            st.rerun()

    title = st.text_input("Titre fournisseur / AliExpress", value=extracted.get("title", ""))
    description = st.text_area("Description fournisseur / AliExpress", value=extracted.get("description", ""), height=180)
    supplier_price = st.text_input("Prix fournisseur détecté optionnel", value=extracted.get("price", ""))
    cost_price = st.number_input("Prix d'achat du produit", min_value=0.0, value=5.0, step=0.5)

    st.subheader("🎯 Stratégie SEO")
    selected_category = st.selectbox("Catégorie / type de boutique", list(CATEGORY_PROMPTS.keys()))
    category_context = st.text_area("Contexte de catégorie modifiable", value=CATEGORY_PROMPTS[selected_category], height=120)
    niche = st.text_input("Client cible / niche", placeholder="Exemple : women gift, gothic fashion, home decor, pet lovers")
    seo_keywords = st.text_input("Mots-clés SEO à ajouter optionnel", placeholder="Exemple : gothic corset, waist trainer, renaissance outfit")
    competitor_text = st.text_area("Fiche concurrente ou inspiration optionnel", height=100, placeholder="Colle ici un titre ou une description concurrente si tu veux t'en inspirer sans copier.")
    tone = st.selectbox("Ton de rédaction", ["Premium and trustworthy", "Warm and emotional", "Minimalist and modern", "Gift-focused", "Luxury boutique"])

    st.subheader("🧠 Prompt IA")
    st.caption("Tu peux modifier le prompt à la main. Même si l'interface est en français, le prompt demande toujours des réponses en anglais.")
    if st.button("Réinitialiser le prompt par défaut"):
        st.session_state["base_prompt"] = DEFAULT_PROMPT
        st.rerun()
    base_prompt = st.text_area("Prompt principal modifiable", value=st.session_state.get("base_prompt", DEFAULT_PROMPT), height=260)
    st.session_state["base_prompt"] = base_prompt

    if st.button("Générer la fiche Etsy en anglais", type="primary"):
        if not openai_key:
            st.error("Ajoute ta clé API OpenAI dans la barre de gauche.")
        elif not title and not description:
            st.error("Extrais les informations depuis l'URL ou colle le titre/la description manuellement.")
        else:
            with st.spinner("Génération de la fiche Etsy en anglais..."):
                try:
                    result = generate_listing(
                        openai_key,
                        {"title": title, "description": description, "price": supplier_price},
                        niche,
                        tone,
                        cost_price,
                        base_prompt,
                        category_context,
                        seo_keywords,
                        competitor_text,
                    )
                    st.session_state["result"] = result
                except Exception as e:
                    st.error(f"La génération a échoué : {e}")

with right:
    st.subheader("✅ Fiche Etsy générée")
    result = st.session_state.get("result")
    if not result:
        st.info("Ta fiche générée apparaîtra ici.")
    else:
        st.markdown("### Titre SEO Etsy")
        st.code(result.get("seo_title", ""), language=None)
        st.markdown("### Description courte")
        st.write(result.get("short_description", ""))
        st.markdown("### Description complète")
        st.write(result.get("full_description", ""))
        st.markdown("### Points clés")
        for b in result.get("bullet_points", []):
            st.write(f"• {b}")
        st.markdown("### 13 tags Etsy")
        tags = result.get("tags", [])
        if isinstance(tags, list):
            st.code(", ".join(tags), language=None)
        else:
            st.code(str(tags), language=None)
        st.markdown("### Prix conseillé")
        st.code(str(result.get("suggested_price", "")), language=None)
        st.markdown("### Bloc prêt à copier-coller")
        st.text_area("Copie ce bloc dans Etsy", value=result.get("copy_paste_block", ""), height=300)
