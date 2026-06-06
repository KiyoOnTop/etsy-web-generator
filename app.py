import json
import re
import requests
from bs4 import BeautifulSoup
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Générateur Etsy SEO V9", page_icon="🛍️", layout="wide")

# -------------------- STYLE --------------------
st.markdown("""
<style>
    .stApp {background: #f6f7fb; color: #111827;}
    h1, h2, h3, h4, label, p, span {color: #111827 !important;}
    .hero {background: linear-gradient(135deg, #ffffff 0%, #eef2ff 100%); border:1px solid #d9def5; border-radius:22px; padding:28px; margin-bottom:18px; box-shadow:0 12px 28px rgba(15,23,42,.08)}
    .card {background:white; border:1px solid #dbe1ee; border-radius:18px; padding:22px; margin:12px 0; box-shadow:0 8px 20px rgba(15,23,42,.06)}
    .small-pill {display:inline-block; background:#ede9fe; color:#6d28d9 !important; padding:6px 11px; border-radius:999px; font-size:13px; font-weight:700; margin-right:8px;}
    .note {background:#eff6ff; border-left:5px solid #3b82f6; padding:12px 14px; border-radius:12px; color:#1e3a8a !important;}
    .warning {background:#fff7ed; border-left:5px solid #f97316; padding:12px 14px; border-radius:12px; color:#7c2d12 !important;}
    .stButton>button {border-radius:12px; font-weight:700;}
    textarea, input, .stSelectbox div[data-baseweb="select"] {background:white !important; color:#111827 !important;}
</style>
""", unsafe_allow_html=True)

# -------------------- HELPERS --------------------
def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

OPENAI_SECRET = get_secret("OPENAI_API_KEY", "")
SCRAPERAPI_SECRET = get_secret("SCRAPERAPI_KEY", "")

def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:9000]

def fetch_url(url: str, scraper_key: str = ""):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    }
    try:
        if scraper_key:
            r = requests.get(
                "http://api.scraperapi.com/",
                params={"api_key": scraper_key, "url": url, "render": "true", "country_code": "fr", "premium": "true"},
                timeout=55,
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
        decoded = []
        for c in candidates:
            try:
                decoded.append(c.encode("utf-8").decode("unicode_escape", errors="ignore"))
            except Exception:
                decoded.append(c)
        title = max(decoded, key=len)

    desc_candidates = re.findall(r'"(?:description|productDescription|seoDescription)"\s*:\s*"(.*?)"', text)
    for c in desc_candidates[:6]:
        try:
            desc_parts.append(c.encode("utf-8").decode("unicode_escape", errors="ignore"))
        except Exception:
            desc_parts.append(c)

    price_candidates = re.findall(r'"(?:salePrice|formattedPrice|price)"\s*:\s*"?([^",}]+)', text)
    if price_candidates:
        price = price_candidates[0]

    title = clean_text(title.replace("| AliExpress", "").replace("- AliExpress", ""))
    description = clean_text("\n".join(desc_parts))
    return {"title": title, "description": description, "price": clean_text(price)}

def recommended_price(cost, shipping, margin_pct, fees_pct):
    denominator = 1 - (margin_pct / 100) - (fees_pct / 100)
    if denominator <= 0.05:
        denominator = 0.05
    return round((cost + shipping) / denominator, 2)

DEFAULT_MAIN_PROMPT = """Tu es un expert en SEO Etsy et en rédaction de fiches produits optimisées.
J’ai une boutique Etsy en dropshipping spécialisée dans les corsets.

À chaque fois que je te donnerai :
• Un nom de produit AliExpress
• Sa description
• Et éventuellement des mots-clés pertinents ou une fiche concurrent

Ta mission est de générer pour moi une fiche produit Etsy complète comprenant :
1. Un titre optimisé SEO clairement en rapport avec les mots-clés, sans spam, mais efficace pour le référencement.
2. Une description optimisée SEO, agréable à lire, fluide et vendeuse, avec un style chaleureux et quelques emojis pour le rendre attrayant, mais pas trop.
3. Une liste de 13 tags Etsy, chacun de maximum 20 caractères, séparés par des virgules, optimisés pour mon SEO Etsy afin que je puisse les copier-coller directement.

Règles importantes :
• Mets toujours les tags sur une seule ligne séparés par des virgules.
• Le texte final doit être en anglais.
• Tu peux t’inspirer de mes concurrents si je t’en fournis, mais ne copie jamais mot pour mot.
• Le style doit rester naturel et vendeur, pas trop robotique ni bourré de mots-clés."""

PRESET_CATEGORIES = {
    "Corsets / Lingerie / Mode alternative": DEFAULT_MAIN_PROMPT,
    "Bijoux / Accessoires": """Tu es un expert SEO Etsy pour bijoux et accessoires. Génère une fiche en anglais avec un titre naturel, une description vendeuse avec quelques emojis, et exactement 13 tags Etsy de 20 caractères maximum. Mets en avant cadeau, style, matière, occasion, élégance, tendance, sans copier les concurrents.""",
    "Décoration maison": """Tu es un expert SEO Etsy pour décoration maison. Génère une fiche en anglais avec un titre SEO naturel, une description chaleureuse et décorative, et exactement 13 tags Etsy de 20 caractères maximum. Mets en avant ambiance, cadeau, style déco, pièce de la maison et usage.""",
    "Animaux / Pet lovers": """Tu es un expert SEO Etsy pour produits animaux et pet lovers. Génère une fiche en anglais avec un titre SEO naturel, une description émotionnelle et vendeuse, et exactement 13 tags Etsy de 20 caractères maximum. Mets en avant propriétaires d'animaux, cadeaux, confort, utilité et style.""",
    "Beauté / Bien-être": """Tu es un expert SEO Etsy pour beauté et bien-être. Génère une fiche en anglais avec un titre SEO naturel, une description rassurante et vendeuse, et exactement 13 tags Etsy de 20 caractères maximum. Évite les promesses médicales et reste naturel.""",
    "Mode / Vêtements": """Tu es un expert SEO Etsy pour mode et vêtements. Génère une fiche en anglais avec un titre SEO naturel, une description vendeuse orientée style, occasions et silhouette, et exactement 13 tags Etsy de 20 caractères maximum.""",
    "Custom / Prompt personnalisé": DEFAULT_MAIN_PROMPT,
}

if "saved_prompts" not in st.session_state:
    st.session_state["saved_prompts"] = dict(PRESET_CATEGORIES)
if "main_prompt" not in st.session_state:
    st.session_state["main_prompt"] = DEFAULT_MAIN_PROMPT
if "extracted" not in st.session_state:
    st.session_state["extracted"] = {"title":"", "description":"", "price":""}

# -------------------- SIDEBAR --------------------
with st.sidebar:
    st.header("⚙️ Réglages")
    openai_key = st.text_input("Clé OpenAI", value=OPENAI_SECRET, type="password")
    scraperapi_key = st.text_input("Clé ScraperAPI", value=SCRAPERAPI_SECRET, type="password")
    st.markdown('<div class="note">Astuce : sauvegarde tes clés dans les Secrets Streamlit pour ne plus les retaper.</div>', unsafe_allow_html=True)
    st.divider()
    st.subheader("💰 Prix")
    margin = st.slider("Marge cible", 20, 90, 45)
    shipping = st.number_input("Livraison estimée", min_value=0.0, value=0.0, step=0.5)
    fees_pct = st.slider("Frais Etsy + paiement", 5, 30, 12)
    currency = st.selectbox("Devise", ["USD", "EUR", "GBP", "CAD", "AUD"], index=1)

# -------------------- HEADER --------------------
st.markdown("""
<div class="hero">
<h1>🛍️ Générateur Etsy SEO</h1>
<p>Interface en français. Les titres, descriptions et tags générés restent en anglais pour le SEO Etsy.</p>
<span class="small-pill">URL AliExpress</span><span class="small-pill">Prompts sauvegardables</span><span class="small-pill">Catégories</span><span class="small-pill">Tags Etsy</span>
</div>
""", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["1️⃣ Produit", "2️⃣ SEO & Prompts", "3️⃣ Résultat"])

# -------------------- TAB PRODUCT --------------------
with tab1:
    st.markdown('<div class="card"><h3>📦 Étape 1 — Récupère ou colle les infos produit</h3><p>Colle un lien AliExpress puis essaie l’extraction. Si AliExpress bloque, colle le titre et la description manuellement.</p></div>', unsafe_allow_html=True)
    url = st.text_input("Lien AliExpress", placeholder="https://www.aliexpress.com/item/...")
    c1, c2, c3 = st.columns([1,1,1])
    with c1:
        if st.button("🔎 Extraire depuis AliExpress", type="primary", use_container_width=True):
            if not url:
                st.warning("Colle d’abord un lien AliExpress.")
            else:
                with st.spinner("Lecture de la page produit..."):
                    html, err = fetch_url(url, scraperapi_key)
                    if err or not html:
                        st.error(f"Extraction impossible : {err}. Colle les infos manuellement.")
                    else:
                        data = extract_product_from_html(html)
                        if not data.get("title") and not data.get("description"):
                            st.warning("AliExpress bloque ou cache les données utiles. Ajoute une clé ScraperAPI ou colle manuellement.")
                        else:
                            st.session_state["extracted"] = data
                            st.success("Infos produit extraites. Vérifie/modifie si besoin.")
                            st.rerun()
    with c2:
        if st.button("🧹 Vider le produit", use_container_width=True):
            st.session_state["extracted"] = {"title":"", "description":"", "price":""}
            st.rerun()
    with c3:
        st.caption("ScraperAPI est recommandé si AliExpress bloque.")

    extracted = st.session_state.get("extracted", {"title":"", "description":"", "price":""})
    left, right = st.columns([1.3, .85])
    with left:
        title = st.text_input("Titre fournisseur / AliExpress", value=extracted.get("title", ""), placeholder="Colle le titre du produit ici")
        description = st.text_area("Description fournisseur / AliExpress", value=extracted.get("description", ""), height=230, placeholder="Colle la description AliExpress ici")
    with right:
        supplier_price = st.text_input("Prix fournisseur détecté", value=extracted.get("price", ""), placeholder="Optionnel")
        cost_price = st.number_input("Prix d'achat du produit", min_value=0.0, value=5.0, step=0.5)
        st.metric("Prix conseillé estimé", f"{recommended_price(cost_price, shipping, margin, fees_pct)} {currency}")
        st.caption("Ce prix est recalculé avec ta marge, tes frais Etsy et la livraison estimée.")

# -------------------- TAB SEO --------------------
with tab2:
    st.markdown('<div class="card"><h3>🎯 Étape 2 — Choisis ou sauvegarde tes prompts</h3><p>Tu peux utiliser ton prompt corset, créer d’autres catégories, modifier le prompt à la main, puis le sauvegarder.</p></div>', unsafe_allow_html=True)

    saved_names = list(st.session_state["saved_prompts"].keys())
    selected_cat = st.selectbox("Catégorie / prompt sauvegardé", saved_names)

    col_load, col_name, col_save = st.columns([.8,1.2,.8])
    with col_load:
        if st.button("📥 Charger ce prompt", use_container_width=True):
            st.session_state["main_prompt"] = st.session_state["saved_prompts"][selected_cat]
            st.success("Prompt chargé.")
            st.rerun()
    with col_name:
        new_prompt_name = st.text_input("Nom pour sauvegarder / nouvelle catégorie", placeholder="Exemple : Bijoux gothiques")
    with col_save:
        if st.button("💾 Sauvegarder", use_container_width=True):
            if not new_prompt_name.strip():
                st.warning("Écris un nom de catégorie avant de sauvegarder.")
            else:
                st.session_state["saved_prompts"][new_prompt_name.strip()] = st.session_state.get("main_prompt", DEFAULT_MAIN_PROMPT)
                st.success("Prompt sauvegardé pour cette session.")
                st.rerun()

    st.markdown('<div class="warning">Important : les prompts sauvegardés ici restent disponibles pendant ta session Streamlit. Pour les garder définitivement, copie-les dans un fichier ou dans le code plus tard.</div>', unsafe_allow_html=True)

    niche = st.text_input("Client cible / niche", placeholder="Exemple : gothic fashion, gift for women, home decor")
    seo_keywords = st.text_input("Mots-clés SEO à ajouter", placeholder="Exemple : gothic corset, waist trainer, renaissance outfit")
    competitor = st.text_area("Fiche concurrente / inspiration", height=95, placeholder="Optionnel : colle ici un titre ou une description concurrente. L’IA ne doit pas copier.")
    tone = st.selectbox("Ton de rédaction", ["Premium and trustworthy", "Warm and emotional", "Minimalist and modern", "Gift-focused", "Luxury boutique"], index=0)

    st.subheader("✍️ Prompt principal modifiable")
    st.session_state["main_prompt"] = st.text_area(
        "Tu peux modifier ce prompt à la main selon ta catégorie",
        value=st.session_state.get("main_prompt", DEFAULT_MAIN_PROMPT),
        height=330,
    )

    col_reset, col_export = st.columns(2)
    with col_reset:
        if st.button("↩️ Remettre le prompt corset par défaut"):
            st.session_state["main_prompt"] = DEFAULT_MAIN_PROMPT
            st.rerun()
    with col_export:
        st.download_button(
            "⬇️ Télécharger mes prompts sauvegardés",
            data=json.dumps(st.session_state["saved_prompts"], ensure_ascii=False, indent=2),
            file_name="mes_prompts_etsy.json",
            mime="application/json",
        )

# -------------------- GENERATION --------------------
def generate_listing(api_key, product_data, niche, tone, cost_price, main_prompt, seo_keywords, competitor):
    client = OpenAI(api_key=api_key)
    sell_price = recommended_price(cost_price, shipping, margin, fees_pct)
    final_prompt = f"""
{main_prompt}

Règle de sortie obligatoire :
- Le contenu final de la fiche Etsy doit être en anglais.
- Retourne uniquement un JSON valide.
- Le titre Etsy doit faire moins de 140 caractères.
- Il faut exactement 13 tags Etsy, sur une seule ligne, chaque tag de 20 caractères maximum si possible.

Données produit :
Titre fournisseur : {product_data.get('title','')}
Description fournisseur : {product_data.get('description','')}
Prix fournisseur détecté : {product_data.get('price','')}

Niche / client cible : {niche}
Mots-clés SEO à intégrer naturellement : {seo_keywords}
Fiche concurrente / inspiration à ne pas copier : {competitor}
Ton demandé : {tone}
Prix d'achat : {cost_price} {currency}
Prix conseillé : {sell_price} {currency}

Return ONLY valid JSON with these keys:
seo_title, short_description, full_description, bullet_points, tags, keywords, category_suggestion, suggested_price, copy_paste_block
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user", "content": final_prompt}],
        temperature=0.7,
        response_format={"type":"json_object"},
    )
    return json.loads(response.choices[0].message.content)

with tab3:
    st.markdown('<div class="card"><h3>🚀 Étape 3 — Génère ta fiche Etsy</h3><p>Le résultat sera en anglais, prêt à copier-coller dans Etsy.</p></div>', unsafe_allow_html=True)
    if st.button("✨ Générer la fiche Etsy", type="primary", use_container_width=True):
        product_title = st.session_state.get("extracted", {}).get("title", "")
        product_desc = st.session_state.get("extracted", {}).get("description", "")
        # Streamlit widgets from other tabs keep values via keys only if key specified; fallback by asking user to use current tab state not possible.
        st.info("Si les champs produit ne sont pas pris en compte, retourne dans l’onglet Produit puis clique de nouveau ici après avoir modifié.")

    # A second generation block outside tabs using current variables only when defined

# Place generation button at bottom using variables if available
st.divider()
st.subheader("✅ Génération rapide")
st.caption("Après avoir rempli Produit + SEO & Prompts, clique ici.")
try:
    current_title = title
    current_desc = description
    current_price = supplier_price
    current_cost = cost_price
    current_niche = niche
    current_tone = tone
    current_keywords = seo_keywords
    current_competitor = competitor
except NameError:
    current_title = current_desc = current_price = current_niche = current_tone = current_keywords = current_competitor = ""
    current_cost = 5.0

if st.button("✨ Générer maintenant", type="primary"):
    if not openai_key:
        st.error("Ajoute ta clé OpenAI dans la barre de gauche.")
    elif not current_title and not current_desc:
        st.error("Ajoute d’abord un titre ou une description produit dans l’onglet Produit.")
    else:
        with st.spinner("Génération de la fiche Etsy en anglais..."):
            try:
                result = generate_listing(
                    openai_key,
                    {"title": current_title, "description": current_desc, "price": current_price},
                    current_niche,
                    current_tone,
                    current_cost,
                    st.session_state.get("main_prompt", DEFAULT_MAIN_PROMPT),
                    current_keywords,
                    current_competitor,
                )
                st.session_state["result"] = result
                st.success("Fiche générée ! Résultat ci-dessous.")
            except Exception as e:
                st.error(f"Erreur génération : {e}")

result = st.session_state.get("result")
if result:
    st.markdown('<div class="card"><h2>📄 Résultat Etsy en anglais</h2></div>', unsafe_allow_html=True)
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
        tag_line = ", ".join(tags)
    else:
        tag_line = str(tags)
    st.code(tag_line, language=None)
    st.markdown("### Suggested price")
    st.code(str(result.get("suggested_price", "")), language=None)
    st.markdown("### Bloc complet à copier")
    st.text_area("Prêt à copier", value=result.get("copy_paste_block", ""), height=320)
