import io
import json
import re
import zipfile
import base64
from urllib.parse import urlparse
from PIL import Image

import requests
import streamlit as st
from bs4 import BeautifulSoup
from openai import OpenAI

st.set_page_config(page_title="Générateur Etsy Premium", page_icon="🛍️", layout="wide")

CSS = """
<style>
:root { --gold:#c8942f; --cream:#fbf7ef; --ink:#1f2937; --muted:#667085; --line:#eadfce; }
.stApp { background: linear-gradient(180deg,#fffaf2 0%,#f7f3ec 100%); color: var(--ink); }
.block-container { padding-top: 1.2rem; max-width: 1500px; }
.hero { background: #fff; border:1px solid var(--line); border-radius:24px; padding:24px 28px; box-shadow:0 10px 30px rgba(31,41,55,.07); margin-bottom:18px; }
.hero h1 { margin:0; font-size:34px; color:#2b2118; }
.hero p { color:var(--muted); margin:8px 0 0; }
.card { background:#fff; border:1px solid var(--line); border-radius:18px; padding:18px; box-shadow:0 8px 22px rgba(31,41,55,.06); margin-bottom:16px; }
.step { display:inline-flex; align-items:center; gap:8px; font-weight:800; color:#5b3b10; margin-bottom:10px; }
.badge { display:inline-flex; align-items:center; justify-content:center; width:26px; height:26px; border-radius:999px; background:var(--gold); color:white; font-size:14px; }
.stButton > button { border-radius:12px !important; font-weight:700 !important; }
.stButton > button[kind="primary"] { background:var(--gold) !important; border-color:var(--gold) !important; color:white !important; }
input, textarea { border-radius:12px !important; }
.stSelectbox div[data-baseweb="select"] { background:#fff !important; color:#111827 !important; }
div[role="listbox"], div[data-baseweb="popover"] { background:#fff !important; color:#111827 !important; }
div[role="option"] { color:#111827 !important; background:#fff !important; }
div[role="option"]:hover { background:#f3eadc !important; }
.small { color:var(--muted); font-size:13px; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ---------- Secrets ----------
def get_secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

OPENAI_SECRET = get_secret("OPENAI_API_KEY", "")
SCRAPERAPI_SECRET = get_secret("SCRAPERAPI_KEY", "")

# ---------- Session ----------
def ss_default(key, value):
    if key not in st.session_state:
        st.session_state[key] = value

ss_default("extracted", {"title":"", "description":"", "price":"", "images":[]})
ss_default("result", None)
ss_default("debug_images", [])
ss_default("selected_photo_urls", [])
ss_default("generated_photos", [])

# ---------- Helpers ----------
def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:10000]

def get_item_id(url: str):
    m = re.search(r"/(?:item|i)/(\d+)\.html", url)
    if not m:
        m = re.search(r"(?:itemId|productId)=([0-9]+)", url)
    return m.group(1) if m else ""

def normalize_url(u: str) -> str:
    if not u:
        return ""
    u = u.replace("\\/", "/").strip().strip('"').strip("'")
    if u.startswith("//"):
        u = "https:" + u
    if u.startswith("http://"):
        u = "https://" + u[7:]
    # remove size suffixes common on AliExpress
    u = re.sub(r"_(\d+)x\d+q\d+\.(jpg|jpeg|png|webp)$", r".\2", u, flags=re.I)
    u = re.sub(r"_(\d+)x\d+\.(jpg|jpeg|png|webp)$", r".\2", u, flags=re.I)
    u = u.replace(".webp", ".jpg") if "alicdn.com" in u else u
    return u

def is_product_img(u: str) -> bool:
    if not u or not u.startswith("http"):
        return False
    lu = u.lower()
    if not any(d in lu for d in ["alicdn.com", "aliexpress-media.com"]):
        return False
    if not any(ext in lu for ext in [".jpg", ".jpeg", ".png", ".webp"]):
        return False
    bad = ["sprite", "logo", "icon", "avatar", "feedback", "ae-logo", "country", "loading", "transparent", "blank"]
    return not any(b in lu for b in bad)

def dedupe(seq):
    out, seen = [], set()
    for x in seq:
        x = normalize_url(x)
        if x and x not in seen and is_product_img(x):
            seen.add(x); out.append(x)
    return out

def build_candidate_urls(url: str):
    urls = [url]
    item_id = get_item_id(url)
    if item_id:
        urls += [
            f"https://www.aliexpress.com/item/{item_id}.html",
            f"https://fr.aliexpress.com/item/{item_id}.html",
            f"https://m.aliexpress.com/item/{item_id}.html",
        ]
    # keep unique
    final=[]
    for u in urls:
        if u and u not in final:
            final.append(u)
    return final

def fetch_html(url: str, scraper_key: str = "", render: bool = False, timeout: int = 35):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    }
    try:
        if scraper_key:
            params = {"api_key": scraper_key, "url": url, "country_code": "us"}
            if render:
                params["render"] = "true"
                timeout = max(timeout, 65)
            r = requests.get("https://api.scraperapi.com/", params=params, timeout=timeout)
        else:
            r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code >= 400:
            return None, f"HTTP {r.status_code}"
        return r.text, None
    except Exception as e:
        return None, str(e)

def extract_json_strings(html: str):
    imgs = []
    # Direct image urls in escaped/unescaped html
    patterns = [
        r"https?:\\?/\\?/[^\"'\\\s]+?alicdn\.com[^\"'\\\s]+?\.(?:jpg|jpeg|png|webp)",
        r"//[^\"'\s]+?alicdn\.com[^\"'\s]+?\.(?:jpg|jpeg|png|webp)",
        r"https?://[^\"'\s]+?alicdn\.com[^\"'\s]+?\.(?:jpg|jpeg|png|webp)",
    ]
    for pat in patterns:
        imgs.extend(re.findall(pat, html, flags=re.I))
    # Common JSON fields
    fields = ["imagePath", "imageUrl", "summImagePath", "magnifierImagePath", "skuPropertyImagePath", "bigPicUrl"]
    for f in fields:
        imgs.extend(re.findall(rf'"{f}"\s*:\s*"(.*?)"', html, flags=re.I))
    # Lists
    list_matches = re.findall(r'"(?:imagePathList|images|productImages)"\s*:\s*\[(.*?)\]', html, flags=re.I|re.S)
    for block in list_matches:
        imgs.extend(re.findall(r'"(.*?)"', block))
    return imgs

def extract_product_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    desc_parts = []
    price = ""
    images = []

    if soup.title and soup.title.string:
        title = soup.title.string
    for prop in ["og:title", "twitter:title"]:
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name":prop})
        if tag and tag.get("content"):
            title = tag["content"]
            break

    for selector in [("name","description"), ("property","og:description")]:
        tag = soup.find("meta", attrs={selector[0]: selector[1]})
        if tag and tag.get("content"):
            desc_parts.append(tag["content"])

    # Normal img tags
    for img in soup.find_all("img"):
        for attr in ["src", "data-src", "data-lazy-src", "data-original"]:
            if img.get(attr):
                images.append(img.get(attr))
        if img.get("srcset"):
            images.extend([p.strip().split(" ")[0] for p in img.get("srcset").split(",")])

    images.extend(extract_json_strings(html))

    # JSON title/description/price search
    candidates = re.findall(r'"(?:subject|title|productTitle|seoTitle)"\s*:\s*"(.*?)"', html, flags=re.I)
    if candidates:
        try:
            title = max([c.encode("utf-8").decode("unicode_escape", errors="ignore") for c in candidates], key=len)
        except Exception:
            title = max(candidates, key=len)
    desc_candidates = re.findall(r'"(?:description|productDescription|seoDescription)"\s*:\s*"(.*?)"', html, flags=re.I|re.S)
    for c in desc_candidates[:5]:
        try:
            desc_parts.append(c.encode("utf-8").decode("unicode_escape", errors="ignore"))
        except Exception:
            desc_parts.append(c)
    price_candidates = re.findall(r'"(?:salePrice|formattedPrice|price|minActivityAmount)"\s*:\s*"?([^",}]+)', html, flags=re.I)
    if price_candidates:
        price = price_candidates[0]

    title = clean_text(title.replace("| AliExpress", "").replace("- AliExpress", ""))
    description = clean_text("\n".join(desc_parts))
    images = dedupe(images)
    # prioritize product gallery CDN /kf/ images
    images = sorted(images, key=lambda u: (0 if "/kf/" in u.lower() else 1, len(u)))[:40]
    return {"title": title, "description": description, "price": clean_text(price), "images": images}

def extract_from_aliexpress(url: str, scraper_key: str = ""):
    logs = []
    best = {"title":"", "description":"", "price":"", "images":[]}
    for candidate in build_candidate_urls(url):
        # 1 direct or scraper no render
        html, err = fetch_html(candidate, scraper_key=scraper_key, render=False, timeout=35)
        logs.append(f"Test sans rendu: {candidate} -> {'OK' if html else err}")
        if html:
            data = extract_product_from_html(html)
            if len(data.get("images", [])) > len(best.get("images", [])):
                best = {**best, **{k:v for k,v in data.items() if v}}
            elif data.get("title") or data.get("description"):
                best.update({k:v for k,v in data.items() if v and not best.get(k)})
            if len(best.get("images", [])) >= 4 and (best.get("title") or best.get("description")):
                break
    # 2 last resort render true only if key and no images
    if scraper_key and len(best.get("images", [])) < 2:
        for candidate in build_candidate_urls(url)[:2]:
            html, err = fetch_html(candidate, scraper_key=scraper_key, render=True, timeout=75)
            logs.append(f"Test avec rendu JS: {candidate} -> {'OK' if html else err}")
            if html:
                data = extract_product_from_html(html)
                if len(data.get("images", [])) > len(best.get("images", [])):
                    best = {**best, **{k:v for k,v in data.items() if v}}
                if len(best.get("images", [])) >= 4:
                    break
    return best, logs

def recommended_price(cost, shipping, margin_pct, fees_pct):
    denom = 1 - margin_pct/100 - fees_pct/100
    if denom <= 0.05: denom = 0.05
    return round((cost + shipping) / denom, 2)

def generate_listing(api_key, data, niche, tone, custom_prompt, keywords, competitor, cost_price, currency, sell_price):
    client = OpenAI(api_key=api_key)
    prompt = f"""
You are an Etsy SEO expert and high-converting product listing copywriter.
Output must be in English.

Main strategy / custom instructions:
{custom_prompt}

Supplier title: {data.get('title','')}
Supplier description: {data.get('description','')}
Supplier price: {data.get('price','')}
Target buyer/niche: {niche}
Extra SEO keywords: {keywords}
Competitor inspiration, do not copy word-for-word: {competitor}
Tone: {tone}
Cost price: {cost_price} {currency}
Suggested selling price: {sell_price} {currency}

Rules:
- Do NOT claim handmade unless explicitly stated.
- Keep Etsy title under 140 characters.
- Generate exactly 13 Etsy tags, each max 20 characters when possible.
- Tags must be a single list.
- Natural conversion-focused English, no keyword stuffing.
- Output valid JSON only.

JSON keys:
seo_title, short_description, full_description, bullet_points, tags, keywords, category_suggestion, suggested_price, copy_paste_block
"""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user", "content":prompt}],
        temperature=0.65,
        response_format={"type":"json_object"},
    )
    return json.loads(resp.choices[0].message.content)

def download_image(url):
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code == 200 and r.content:
            return r.content
    except Exception:
        return None
    return None

def make_zip(urls):
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        count = 0
        for i,u in enumerate(urls, start=1):
            content = download_image(u)
            if content:
                ext = ".jpg"
                if ".png" in u.lower(): ext = ".png"
                elif ".webp" in u.lower(): ext = ".webp"
                z.writestr(f"aliexpress_photo_{i}{ext}", content)
                count += 1
        if count == 0:
            z.writestr("aucune_image.txt", "Aucune image n'a pu etre telechargee.")
    mem.seek(0)
    return mem.getvalue()


def image_bytes_to_png_bytes(content: bytes):
    """Convertit une image téléchargée en PNG carré compatible édition IA."""
    try:
        img = Image.open(io.BytesIO(content)).convert("RGBA")
        # Resize without cropping too aggressively: keep full product visible on square canvas
        max_side = max(img.size)
        canvas = Image.new("RGBA", (max_side, max_side), (255, 255, 255, 0))
        x = (max_side - img.size[0]) // 2
        y = (max_side - img.size[1]) // 2
        canvas.paste(img, (x, y), img if img.mode == "RGBA" else None)
        canvas = canvas.convert("RGB").resize((1024, 1024))
        out = io.BytesIO()
        canvas.save(out, format="PNG")
        out.seek(0)
        return out.getvalue()
    except Exception:
        return content

PHOTO_PROMPT_DEFAULT = """OBJECTIVE:
Create a realistic, professional, luxury ecommerce photo from the reference image.

ABSOLUTE PRODUCT RULES:
- Keep the product exactly identical to the original image.
- Do not change the product shape, color, fabric, lace, pattern, stitching, seams, print, buttons, ribbons, accessories, proportions, or structure.
- Do not redesign the product.
- Do not invent new product details.
- The product must look like the same real item the customer will receive.

WHAT MAY CHANGE:
- Background
- Decor
- Lighting
- Overall environment
- Model appearance if a model is present, while keeping the exact same product and view direction

VIEW / ANGLE RULES:
- Preserve the original viewing angle and product orientation.
- If the reference image is a back view, the result must show the model/product from the back.
- If the reference image is a front view, the result must show the model/product from the front.
- If the reference image is a side view, the result must show the model/product from the side.
- Never turn a back-view product into a front-view product.

STYLE:
- Ultra realistic luxury fashion ecommerce photography.
- Natural human model, realistic skin, realistic proportions.
- Elegant premium boutique interior, luxury apartment, Parisian room, or high-end hotel suite.
- Soft natural daylight or professional studio lighting.
- No artificial AI look, no plastic skin, no fantasy style.
- Etsy-ready premium product photo.
- Square 1:1 composition.
- No text, no logo, no watermark."""

def build_photo_prompt(base_prompt: str, style: str, view: str, change_model: bool):
    view_map = {
        "Automatique": "Analyze the reference image and preserve the exact original view direction.",
        "Face": "The generated image must be a FRONT VIEW. Show the product from the front.",
        "Dos": "The generated image must be a BACK VIEW. Show the product from the back. Do not show the front.",
        "Latérale": "The generated image must be a SIDE VIEW. Show the product from the side.",
        "Gros plan": "Create a close-up product detail shot while preserving exact details.",
        "Flat lay": "Create a flat lay product photo only if the reference is flat lay; otherwise preserve the original view.",
    }
    style_map = {
        "Luxury Interior": "Use an elegant luxury interior, Parisian apartment, soft warm daylight, premium boutique atmosphere.",
        "Romantic Boutique": "Use a romantic boutique atmosphere with soft flowers, warm neutral tones, elegant decor.",
        "Fashion Editorial": "Use high-end fashion editorial photography, realistic magazine style, premium lighting.",
        "Clean Ecommerce": "Use a clean premium ecommerce studio background, minimal decor, very realistic product focus.",
    }
    model_rule = "You may use a different realistic professional model if a model is present, but the product must remain exactly identical." if change_model else "Do not change the model/person; only improve background, lighting, and decor."
    return f"""{base_prompt}

SELECTED STYLE:
{style_map.get(style, style)}

SELECTED VIEW:
{view_map.get(view, view)}

MODEL RULE:
{model_rule}

Final reminder: edit the reference image; do not create a different product."""

def generate_premium_photo(api_key: str, image_url: str, prompt: str):
    content = download_image(image_url)
    if not content:
        raise RuntimeError("Impossible de télécharger l'image sélectionnée.")
    png = image_bytes_to_png_bytes(content)
    client = OpenAI(api_key=api_key)
    image_file = io.BytesIO(png)
    image_file.name = "reference.png"
    # Uses image editing with the selected AliExpress photo as visual reference.
    resp = client.images.edit(
        model="gpt-image-1",
        image=image_file,
        prompt=prompt,
        size="1024x1024",
        quality="high",
        n=1,
    )
    b64 = resp.data[0].b64_json
    return base64.b64decode(b64)

def make_generated_zip(items):
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        if not items:
            z.writestr("aucune_photo_generee.txt", "Aucune photo premium n'a encore ete generee.")
        for i, it in enumerate(items, start=1):
            z.writestr(f"photo_premium_{i}.png", it["bytes"])
    mem.seek(0)
    return mem.getvalue()

# ---------- UI ----------
st.markdown('<div class="hero"><h1>🛍️ Générateur de Fiches Etsy Premium</h1><p>Extraction AliExpress + photos produit + génération photos premium + fiche Etsy SEO en anglais.</p></div>', unsafe_allow_html=True)

with st.sidebar:
    st.subheader("🔐 Clés API")
    openai_key = st.text_input("Clé OpenAI", value=OPENAI_SECRET, type="password")
    scraperapi_key = st.text_input("Clé ScraperAPI", value=SCRAPERAPI_SECRET, type="password")
    st.info("Astuce : si les photos ne sortent pas, essaie avec un lien www.aliexpress.com plutôt que fr.aliexpress.com.")
    st.subheader("💰 Prix")
    margin = st.slider("Marge cible", 20, 90, 45)
    shipping = st.number_input("Livraison estimée", min_value=0.0, value=0.0, step=0.5)
    fees_pct = st.slider("Frais Etsy + paiement", 5, 30, 12)
    currency = st.selectbox("Devise", ["EUR", "USD", "GBP", "CAD", "AUD"], index=0)

col1, col2, col3 = st.columns([0.95, 1.1, 1.0])

with col1:
    st.markdown('<div class="card"><div class="step"><span class="badge">1</span>Extraire de AliExpress</div>', unsafe_allow_html=True)
    url = st.text_input("Lien AliExpress", placeholder="https://www.aliexpress.com/item/100500....html")
    if st.button("Extraire infos + photos", type="primary", use_container_width=True):
        if not url:
            st.warning("Colle d'abord un lien AliExpress.")
        else:
            with st.spinner("Extraction en cours... AliExpress peut être lent."):
                data, logs = extract_from_aliexpress(url, scraperapi_key)
                st.session_state.extracted = data
                st.session_state.debug_images = logs
                if data.get("images"):
                    st.success(f"Extraction réussie : {len(data['images'])} image(s) trouvée(s).")
                else:
                    st.warning("Aucune photo produit trouvée automatiquement. Utilise le mode manuel ci-dessous.")
    if st.button("Vider", use_container_width=True):
        st.session_state.extracted = {"title":"", "description":"", "price":"", "images":[]}
        st.session_state.result = None
        st.rerun()
    with st.expander("Mode manuel : coller des URLs d'images"):
        manual = st.text_area("Une URL d'image par ligne", placeholder="https://ae01.alicdn.com/kf/....jpg")
        if st.button("Ajouter ces photos"):
            imgs = dedupe(manual.splitlines())
            current = st.session_state.extracted.get("images", [])
            st.session_state.extracted["images"] = dedupe(current + imgs)
            st.success(f"{len(imgs)} image(s) ajoutée(s).")
            st.rerun()
    with st.expander("Debug extraction"):
        for l in st.session_state.debug_images:
            st.caption(l)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="step"><span class="badge">2</span>Photos extraites</div>', unsafe_allow_html=True)
    imgs = st.session_state.extracted.get("images", [])
    selected = []
    if imgs:
        st.caption("Sélectionne uniquement les vraies photos produit. Évite tableaux de tailles, logos et infographies.")
        cols = st.columns(2)
        for i,u in enumerate(imgs[:24]):
            with cols[i%2]:
                st.image(u, use_container_width=True)
                if st.checkbox("Sélectionner", key=f"imgsel_{i}", value=i<4):
                    selected.append(u)
        st.session_state.selected_photo_urls = selected
        if selected:
            st.download_button("Télécharger les photos sélectionnées (ZIP)", data=make_zip(selected), file_name="photos_aliexpress.zip", mime="application/zip", use_container_width=True)
    else:
        st.info("Aucune photo affichée pour le moment.")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="step"><span class="badge">3</span>✨ Génération photos premium</div>', unsafe_allow_html=True)
    st.caption("Utilise les photos sélectionnées comme référence. Le produit doit rester identique, seul le décor/mannequin/lumière change.")
    photo_style = st.selectbox("Style photo", ["Luxury Interior", "Romantic Boutique", "Fashion Editorial", "Clean Ecommerce"], index=0)
    photo_view = st.selectbox("Vue à respecter", ["Automatique", "Face", "Dos", "Latérale", "Gros plan", "Flat lay"], index=0)
    change_model = st.checkbox("Changer le mannequin si présent", value=True)
    photos_to_generate = st.slider("Nombre maximum de photos à générer", 1, 8, 2)
    with st.expander("Modifier le prompt photo"):
        photo_prompt_base = st.text_area("Prompt photo personnalisé", value=PHOTO_PROMPT_DEFAULT, height=360)
    if st.button("✨ Générer les photos premium", type="primary", use_container_width=True):
        if not openai_key:
            st.error("Ajoute ta clé OpenAI dans la barre de gauche.")
        elif not st.session_state.selected_photo_urls:
            st.error("Sélectionne au moins une photo AliExpress.")
        else:
            prompt_final = build_photo_prompt(photo_prompt_base, photo_style, photo_view, change_model)
            todo = st.session_state.selected_photo_urls[:photos_to_generate]
            generated = []
            prog = st.progress(0)
            for idx, img_url in enumerate(todo, start=1):
                try:
                    with st.spinner(f"Génération photo {idx}/{len(todo)}..."):
                        out = generate_premium_photo(openai_key, img_url, prompt_final)
                        generated.append({"bytes": out, "source": img_url, "style": photo_style, "view": photo_view})
                except Exception as e:
                    st.error(f"Erreur photo {idx}: {e}")
                prog.progress(idx / len(todo))
            if generated:
                st.session_state.generated_photos = generated
                st.success(f"{len(generated)} photo(s) premium générée(s).")
                st.rerun()
    gen = st.session_state.generated_photos
    if gen:
        st.markdown("**Photos premium générées**")
        gcols = st.columns(2)
        for i,it in enumerate(gen):
            with gcols[i%2]:
                st.image(it["bytes"], use_container_width=True)
        st.download_button("Télécharger les photos premium (ZIP)", data=make_generated_zip(gen), file_name="photos_premium_etsy.zip", mime="application/zip", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="card"><div class="step"><span class="badge">4</span>Informations produit</div>', unsafe_allow_html=True)
    ext = st.session_state.extracted
    title = st.text_input("Titre fournisseur / AliExpress", value=ext.get("title", ""))
    supplier_price = st.text_input("Prix fournisseur détecté", value=ext.get("price", ""))
    desc = st.text_area("Description fournisseur / AliExpress", value=ext.get("description", ""), height=210)
    cost_price = st.number_input("Prix d'achat du produit", min_value=0.0, value=5.0, step=0.5)
    sell_price = recommended_price(cost_price, shipping, margin, fees_pct)
    st.metric("Prix conseillé estimé", f"{sell_price} {currency}")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="step"><span class="badge">5</span>SEO & Prompt</div>', unsafe_allow_html=True)
    category = st.selectbox("Catégorie / type de boutique", ["Corsets / Lingerie / Mode alternative", "Bijoux / Accessoires", "Décoration maison", "Animaux / Pet lovers", "Beauté / Bien-être", "Mode générale", "Prompt personnalisé"])
    default_prompts = {
        "Corsets / Lingerie / Mode alternative": "I run an Etsy store specialized in corsets, lingerie-inspired fashion, gothic fashion, renaissance fashion, burlesque fashion, shapewear and alternative fashion. Focus on style, confidence, giftability, comfort, outfit ideas and conversion-focused Etsy SEO.",
        "Bijoux / Accessoires": "I run an Etsy store selling jewelry and fashion accessories. Focus on giftability, elegance, occasions, materials, style and Etsy SEO.",
        "Décoration maison": "I run an Etsy store selling home decor. Focus on cozy interiors, giftability, aesthetic style, room decor, premium presentation and Etsy SEO.",
        "Animaux / Pet lovers": "I run an Etsy store for pet lovers. Focus on emotional connection, useful benefits, giftability, comfort and Etsy SEO.",
        "Beauté / Bien-être": "I run an Etsy store in beauty and wellness. Focus on self-care, routine, benefits, premium feel and Etsy SEO.",
        "Mode générale": "I run an Etsy fashion store. Focus on style, outfit ideas, confidence, giftability, occasions and Etsy SEO.",
        "Prompt personnalisé": "Write a natural, persuasive, SEO-optimized Etsy listing in English. Avoid keyword stuffing and do not copy competitors word-for-word.",
    }
    custom_prompt = st.text_area("Prompt principal modifiable", value=default_prompts[category], height=130)
    niche = st.text_input("Client cible / niche", placeholder="ex: gothic fashion, gift for women, vintage outfit")
    keywords = st.text_input("Mots-clés SEO à ajouter", placeholder="ex: gothic corset, waist trainer, renaissance outfit")
    competitor = st.text_area("Fiche concurrente / inspiration", placeholder="Optionnel : colle un titre ou une description concurrente. L'IA ne doit pas copier.", height=90)
    tone = st.selectbox("Ton de rédaction", ["Premium and trustworthy", "Warm and emotional", "Luxury boutique", "Gift-focused", "Minimalist and modern"])
    st.markdown('</div>', unsafe_allow_html=True)

with col3:
    st.markdown('<div class="card"><div class="step"><span class="badge">6</span>Générer la fiche Etsy</div>', unsafe_allow_html=True)
    if st.button("Générer la fiche complète", type="primary", use_container_width=True):
        if not openai_key:
            st.error("Ajoute ta clé OpenAI dans la barre de gauche.")
        elif not title and not desc:
            st.error("Ajoute ou extrais un titre/description produit.")
        else:
            with st.spinner("Génération de la fiche Etsy en anglais..."):
                try:
                    res = generate_listing(openai_key, {"title": title, "description": desc, "price": supplier_price}, niche, tone, custom_prompt, keywords, competitor, cost_price, currency, sell_price)
                    st.session_state.result = res
                except Exception as e:
                    st.error(f"Erreur génération : {e}")
    res = st.session_state.result
    if res:
        st.subheader("Titre SEO")
        st.code(res.get("seo_title", ""), language=None)
        st.subheader("Description courte")
        st.write(res.get("short_description", ""))
        st.subheader("Description complète")
        st.write(res.get("full_description", ""))
        st.subheader("Points clés")
        for b in res.get("bullet_points", []):
            st.write("• " + str(b))
        st.subheader("13 tags Etsy")
        tags = res.get("tags", [])
        st.code(", ".join(tags), language=None)
        st.subheader("Bloc à copier")
        st.text_area("Copier-coller", value=res.get("copy_paste_block", ""), height=260)
    else:
        st.info("Ta fiche générée apparaîtra ici.")
    st.markdown('</div>', unsafe_allow_html=True)

st.caption("Important : vérifie toujours que les photos et textes représentent fidèlement le produit vendu et respectent les règles Etsy.")
