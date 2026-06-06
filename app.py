import base64
import io
import json
import re
import zipfile
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Générateur Etsy Premium", page_icon="🦋", layout="wide")

CSS = """
<style>
:root{--gold:#c9932f;--purple:#6d4cc2;--cream:#fffaf1;--border:#eadfcd;--text:#1f2937;--muted:#6b7280;}
.stApp{background:linear-gradient(180deg,#fffaf1 0%,#f7f1e8 100%);color:var(--text);} 
.block-container{padding-top:1.3rem;max-width:1500px;}
[data-testid="stHeader"]{background:transparent;}
.hero{background:rgba(255,255,255,.88);border:1px solid var(--border);border-radius:22px;padding:22px 26px;margin-bottom:18px;box-shadow:0 12px 35px rgba(64,41,10,.08)}
.hero h1{font-size:30px;margin:0;color:#26211a}.hero p{margin:6px 0 0;color:#6b5d4d}
.card{background:rgba(255,255,255,.92);border:1px solid var(--border);border-radius:18px;padding:18px;margin-bottom:16px;box-shadow:0 10px 25px rgba(64,41,10,.06)}
.step{display:inline-block;background:var(--purple);color:white;border-radius:999px;padding:3px 9px;font-weight:700;margin-right:8px}.section-title{font-weight:800;font-size:18px;color:#2d251c;margin-bottom:8px}
.small-note{color:var(--muted);font-size:13px}.success-box{background:#edfdf1;border:1px solid #b7efc3;color:#166534;border-radius:12px;padding:12px;margin:8px 0}.warn-box{background:#fff7db;border:1px solid #f4d782;color:#7a4b00;border-radius:12px;padding:12px;margin:8px 0}
.stButton>button{border-radius:12px;font-weight:700;border:1px solid #d2a44b;background:linear-gradient(180deg,#d7a33c,#bd8121);color:white;min-height:42px}
.stDownloadButton>button{border-radius:12px;font-weight:700;border:1px solid #d6c6a9;background:#fff;color:#533b1b;min-height:40px}
input, textarea, [data-baseweb="select"]{background:white!important;color:#111827!important;border-color:#d7c8ad!important;border-radius:12px!important}
div[role="listbox"], ul[role="listbox"]{background:white!important;color:#111827!important}div[role="option"]{color:#111827!important;background:white!important}div[role="option"]:hover{background:#f3eadb!important}
img{border-radius:12px}.photo-tile{border:1px solid var(--border);border-radius:14px;padding:8px;background:white}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

DEFAULT_PROMPT = """You are a professional luxury ecommerce photographer and image editor.

OBJECTIVE:
Keep the original product exactly identical to the reference image.
Only improve the presentation.

ABSOLUTE RULES:
- Do not change the product shape, color, pattern, fabric, lace, seams, stitching, accessories, proportions, or design.
- Do not redesign the product.
- If the original image is a back view, keep a back view.
- If the original image is a front view, keep a front view.
- If the original image is a side view, keep a side view.
- Preserve the original camera angle and product orientation.

YOU MAY CHANGE ONLY:
- background
- decor/environment
- lighting
- model/person if present, while keeping the product identical
- overall photography style

STYLE:
Ultra realistic luxury boutique interior, elegant warm natural light, professional ecommerce photography, premium Etsy listing quality, no AI look, no fantasy, no text, no logo, no watermark, square 1:1."""

CATEGORY_PROMPTS = {
    "Corsets / Lingerie / Mode alternative": "I run an Etsy store specialized in corsets, lingerie-inspired fashion, gothic fashion, renaissance fashion, burlesque fashion, shapewear and alternative fashion. Focus on style, confidence, giftability, comfort, outfit ideas and conversion-focused Etsy SEO.",
    "Bijoux / Accessoires": "I run an Etsy store specialized in jewelry and accessories. Focus on giftability, elegance, everyday wear, occasion styling and premium presentation.",
    "Décoration maison": "I run an Etsy store specialized in home decor. Focus on cozy interiors, giftability, aesthetic rooms, premium decor and emotional buying triggers.",
    "Animaux / Pet lovers": "I run an Etsy store specialized in pet lover products. Focus on emotional connection, practical benefits, gift ideas and cute but trustworthy copy.",
    "Beauté / Bien-être": "I run an Etsy store specialized in beauty and wellness products. Focus on self-care, routine, giftability and premium lifestyle benefits.",
    "Mode générale": "I run an Etsy store specialized in fashion products. Focus on outfit ideas, style, comfort, confidence and conversion-focused Etsy SEO.",
    "Prompt personnalisé": "Describe your store category, target buyer, SEO direction and style here."
}

def get_secret(name, default=""):
    try: return st.secrets.get(name, default)
    except Exception: return default

OPENAI_SECRET = get_secret("OPENAI_API_KEY", "")
SCRAPERAPI_SECRET = get_secret("SCRAPERAPI_KEY", "")

with st.sidebar:
    st.markdown("### ⚙️ Réglages")
    openai_key = st.text_input("Clé OpenAI", value=OPENAI_SECRET, type="password")
    scraperapi_key = st.text_input("Clé ScraperAPI", value=SCRAPERAPI_SECRET, type="password")
    margin = st.slider("Marge cible", 20, 90, 45)
    shipping = st.number_input("Livraison estimée", min_value=0.0, value=0.0, step=0.5)
    fees_pct = st.slider("Frais Etsy + paiement", 5, 30, 12)
    currency = st.selectbox("Devise", ["EUR","USD","GBP","CAD","AUD"])
    st.info("Ajoute les clés dans Streamlit Secrets pour ne plus les retaper.")


def clean_text(text):
    if not text: return ""
    text = re.sub(r"\\/", "/", text)
    text = text.encode("utf-8", "ignore").decode("unicode_escape", "ignore") if "\\u" in text else text
    text = re.sub(r"\s+", " ", text).strip()
    return text[:10000]


def normalize_img_url(u):
    if not u: return ""
    u = u.replace("\\/", "/").strip().strip('"\'')
    if u.startswith("//"): u = "https:" + u
    if u.startswith("http://"): u = "https://" + u[7:]
    u = re.sub(r"_(\d+x\d+|\d+x\d+q\d+|\d+x\d+xz)\.(jpg|jpeg|png|webp)$", r".\2", u, flags=re.I)
    u = re.sub(r"\.jpg_.*$", ".jpg", u, flags=re.I)
    u = re.sub(r"\.png_.*$", ".png", u, flags=re.I)
    u = re.sub(r"\.webp_.*$", ".webp", u, flags=re.I)
    return u


def is_product_image(u):
    if not u: return False
    low = u.lower()
    if not any(ext in low for ext in [".jpg", ".jpeg", ".png", ".webp"]): return False
    bad = ["logo", "sprite", "avatar", "banner", "icon", "qr", "ae01.alicdn.com/kf/s", "gloimg"]
    if any(b in low for b in bad): return False
    return ("alicdn.com" in low or "aliexpress-media" in low or "ae01" in low)


def fetch_url(url, scraper_key=""):
    headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36","Accept-Language":"en-US,en;q=0.9,fr;q=0.8"}
    try:
        if scraper_key:
            # Faster first pass, no JS render. Better for images embedded in HTML.
            r=requests.get("https://api.scraperapi.com/", params={"api_key":scraper_key,"url":url,"country_code":"us","premium":"true"}, timeout=35)
            if r.status_code >= 400 or len(r.text) < 1000:
                r=requests.get("https://api.scraperapi.com/", params={"api_key":scraper_key,"url":url,"render":"true","country_code":"us","premium":"true"}, timeout=70)
        else:
            r=requests.get(url,headers=headers,timeout=25)
        if r.status_code>=400: return None, f"HTTP {r.status_code}"
        return r.text, None
    except Exception as e:
        return None, str(e)


def extract_images_from_html(html):
    urls=[]
    soup=BeautifulSoup(html,"html.parser")
    # 1 meta og images
    for m in soup.find_all("meta"):
        c=m.get("content") or ""
        if "image" in (m.get("property","")+m.get("name","")).lower() and is_product_image(c):
            urls.append(normalize_img_url(c))
    # 2 img tags and srcsets
    for img in soup.find_all("img"):
        for attr in ["src","data-src","data-lazy-src","data-original","data-spm-anchor-id"]:
            u=img.get(attr)
            if is_product_image(u): urls.append(normalize_img_url(u))
        srcset=img.get("srcset") or img.get("data-srcset") or ""
        for part in srcset.split(","):
            u=part.strip().split(" ")[0]
            if is_product_image(u): urls.append(normalize_img_url(u))
    # 3 regex on whole HTML, catches gallery JSON
    patterns=[
        r'https?:\\?/\\?/[^"\'<> ]*alicdn\.com[^"\'<> ]*?\.(?:jpg|jpeg|png|webp)[^"\'<> ]*',
        r'//[^"\'<> ]*alicdn\.com[^"\'<> ]*?\.(?:jpg|jpeg|png|webp)[^"\'<> ]*',
        r'"(imageUrl|imgUrl|bigPic|picUrl|summImagePath|mainImage)"\s*:\s*"([^"<>]+)"'
    ]
    for pat in patterns[:2]:
        for u in re.findall(pat, html, flags=re.I):
            if isinstance(u, tuple): u=u[-1]
            if is_product_image(u): urls.append(normalize_img_url(u))
    for match in re.findall(patterns[2], html, flags=re.I):
        u=match[1]
        if is_product_image(u): urls.append(normalize_img_url(u))
    # dedupe while preserving order
    seen=set(); out=[]
    for u in urls:
        u=normalize_img_url(u)
        if u and u not in seen and is_product_image(u):
            seen.add(u); out.append(u)
    # prefer larger product images, remove tiny thumbnails if duplicate base likely
    return out[:30]


def extract_product_from_html(html):
    soup=BeautifulSoup(html,"html.parser")
    title=""; desc=[]; price=""
    if soup.title and soup.title.string: title=soup.title.string
    og=soup.find("meta", property="og:title")
    if og and og.get("content"): title=og["content"]
    md=soup.find("meta", attrs={"name":"description"}) or soup.find("meta", property="og:description")
    if md and md.get("content"): desc.append(md["content"])
    candidates=re.findall(r'"(?:subject|title|productTitle)"\s*:\s*"(.*?)"', html)
    if candidates:
        title=max([clean_text(c) for c in candidates], key=len)
    for c in re.findall(r'"(?:description|productDescription|seoDescription)"\s*:\s*"(.*?)"', html)[:6]:
        desc.append(clean_text(c))
    pc=re.findall(r'"(?:salePrice|formattedPrice|price)"\s*:\s*"?([^",}]+)', html)
    if pc: price=clean_text(pc[0])
    title=clean_text(title.replace("| AliExpress","").replace("- AliExpress","")).strip()
    return {"title":title,"description":clean_text("\n".join(desc)),"price":price,"images":extract_images_from_html(html)}


def recommended_price(cost, shipping, margin_pct, fees_pct):
    denom=1-(margin_pct/100)-(fees_pct/100)
    if denom<=0.05: denom=0.05
    return round((cost+shipping)/denom,2)


def generate_listing(api_key, data, niche, tone, cost_price, category_context, keywords, competitor):
    client=OpenAI(api_key=api_key)
    sell_price=recommended_price(cost_price, shipping, margin, fees_pct)
    prompt=f"""
You are an Etsy SEO expert and high-converting product listing copywriter.

Store/category context:
{category_context}

Generate a complete Etsy product listing in ENGLISH from supplier data.

Rules:
- Do NOT claim handmade unless explicitly provided.
- Keep title under 140 characters.
- Description must be natural, warm, persuasive, SEO optimized, not robotic.
- Use a few relevant emojis, not too many.
- Generate exactly 13 Etsy tags, each max 20 characters if possible.
- Tags must be on one line separated by commas in copy_paste_block.
- Do not copy competitor text word for word.
- Avoid keyword stuffing.

Supplier title: {data.get('title','')}
Supplier description: {data.get('description','')}
Supplier price: {data.get('price','')}
Extra SEO keywords: {keywords}
Competitor inspiration: {competitor}
Target buyer/niche: {niche}
Tone: {tone}
Cost price: {cost_price} {currency}
Suggested selling price: {sell_price} {currency}

Return ONLY valid JSON with keys:
seo_title, short_description, full_description, bullet_points, tags, keywords, category_suggestion, suggested_price, copy_paste_block
"""
    r=client.chat.completions.create(model="gpt-4o-mini",messages=[{"role":"user","content":prompt}],temperature=0.7,response_format={"type":"json_object"})
    return json.loads(r.choices[0].message.content)


def download_image(url):
    try:
        r=requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=20)
        if r.status_code==200 and r.content:
            return r.content
    except Exception: pass
    return None


def make_zip(image_urls):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as z:
        for i,u in enumerate(image_urls,1):
            data=download_image(u)
            if data:
                ext="jpg"
                path=urlparse(u).path.lower()
                if ".png" in path: ext="png"
                elif ".webp" in path: ext="webp"
                z.writestr(f"aliexpress_photo_{i}.{ext}", data)
    buf.seek(0)
    return buf

# UI
st.markdown('<div class="hero"><h1>🦋 Générateur de Fiches Etsy Premium</h1><p>Extraction AliExpress + photos + fiche produit Etsy. Interface en français, résultats SEO en anglais.</p></div>', unsafe_allow_html=True)

# State defaults
if "extracted" not in st.session_state: st.session_state.extracted={"title":"","description":"","price":"","images":[]}
if "result" not in st.session_state: st.session_state.result=None

c1,c2,c3 = st.columns([1.05,1.1,1])
with c1:
    st.markdown('<div class="card"><div class="section-title"><span class="step">1</span>Extraire AliExpress</div>', unsafe_allow_html=True)
    url=st.text_input("Lien AliExpress", placeholder="https://fr.aliexpress.com/item/100500...")
    if st.button("🔎 Extraire infos + photos", use_container_width=True):
        if not url:
            st.warning("Colle un lien AliExpress d'abord.")
        else:
            with st.spinner("Extraction en cours..."):
                html,err=fetch_url(url,scraperapi_key)
                if err or not html:
                    st.error(f"Extraction impossible : {err}. Colle les infos manuellement.")
                else:
                    data=extract_product_from_html(html)
                    st.session_state.extracted=data
                    n=len(data.get("images",[]))
                    if n:
                        st.success(f"Extraction réussie : infos + {n} photos récupérées.")
                    else:
                        st.warning("Infos récupérées, mais aucune photo trouvée. Essaie avec un lien www.aliexpress.com ou ScraperAPI.")
    if st.button("🧹 Vider", use_container_width=True):
        st.session_state.extracted={"title":"","description":"","price":"","images":[]}; st.session_state.result=None; st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="section-title">📸 Photos extraites</div>', unsafe_allow_html=True)
    imgs=st.session_state.extracted.get("images",[])
    selected=[]
    if imgs:
        cols=st.columns(3)
        for i,u in enumerate(imgs[:18]):
            with cols[i%3]:
                st.image(u, use_container_width=True)
                if st.checkbox("Sélectionner", key=f"sel_{i}", value=i<6): selected.append(u)
        if selected:
            st.download_button("⬇️ Télécharger les photos sélectionnées", data=make_zip(selected), file_name="photos_aliexpress.zip", mime="application/zip", use_container_width=True)
    else:
        st.caption("Les photos apparaîtront ici après extraction.")
    st.markdown('</div>', unsafe_allow_html=True)

with c2:
    st.markdown('<div class="card"><div class="section-title"><span class="step">2</span>Informations produit</div>', unsafe_allow_html=True)
    ex=st.session_state.extracted
    title=st.text_input("Titre fournisseur / AliExpress", value=ex.get("title",""))
    description=st.text_area("Description fournisseur / AliExpress", value=ex.get("description",""), height=180)
    pcol1,pcol2=st.columns(2)
    with pcol1: supplier_price=st.text_input("Prix fournisseur détecté", value=ex.get("price",""))
    with pcol2: cost_price=st.number_input("Prix d'achat du produit", min_value=0.0, value=5.0, step=0.5)
    st.markdown(f"**Prix conseillé estimé : {recommended_price(cost_price, shipping, margin, fees_pct)} {currency}**")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="section-title"><span class="step">3</span>SEO & Prompt</div>', unsafe_allow_html=True)
    cat=st.selectbox("Catégorie / type de boutique", list(CATEGORY_PROMPTS.keys()))
    category_context=st.text_area("Contexte de catégorie modifiable", value=CATEGORY_PROMPTS[cat], height=100)
    niche=st.text_input("Client cible / niche", placeholder="ex: gothic fashion, gift for women")
    keywords=st.text_input("Mots-clés SEO à ajouter", placeholder="ex: gothic corset, waist trainer, renaissance outfit")
    competitor=st.text_area("Fiche concurrente / inspiration", placeholder="Optionnel", height=80)
    tone=st.selectbox("Ton de rédaction", ["Premium and trustworthy","Warm and emotional","Luxury boutique","Gift-focused","Minimalist and modern"])
    if st.button("✍️ Générer la fiche Etsy", use_container_width=True):
        if not openai_key:
            st.error("Ajoute ta clé OpenAI dans la barre de gauche.")
        elif not title and not description:
            st.error("Extrais ou colle au minimum un titre/description.")
        else:
            with st.spinner("Génération de la fiche Etsy en anglais..."):
                try:
                    st.session_state.result=generate_listing(openai_key,{"title":title,"description":description,"price":supplier_price},niche,tone,cost_price,category_context,keywords,competitor)
                    st.success("Fiche générée.")
                except Exception as e: st.error(f"Erreur génération : {e}")
    st.markdown('</div>', unsafe_allow_html=True)

with c3:
    st.markdown('<div class="card"><div class="section-title"><span class="step">4</span>Prompt photo</div>', unsafe_allow_html=True)
    st.caption("Pour générer des images, utilise un vrai outil d'édition image-to-image. Ce prompt est prêt à copier.")
    view=st.selectbox("Vue de la photo source", ["Automatique / garder l'angle original","Face","Dos","Latérale","Gros plan","Flat lay"])
    style=st.selectbox("Style décor", ["Luxury Interior","Romantic Boutique","Fashion Editorial","Clean Ecommerce","Parisian Apartment","Luxury Hotel Suite"])
    photo_prompt=st.text_area("Prompt image personnalisable", value=DEFAULT_PROMPT+f"\n\nSelected view instruction: {view}.\nSelected style: {style}.", height=260)
    st.download_button("⬇️ Télécharger le prompt photo", data=photo_prompt, file_name="prompt_photo.txt", mime="text/plain", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="section-title"><span class="step">5</span>Résultat Etsy</div>', unsafe_allow_html=True)
    res=st.session_state.result
    if not res:
        st.info("La fiche générée apparaîtra ici.")
    else:
        st.markdown("**Titre SEO**")
        st.code(res.get("seo_title",""), language=None)
        st.markdown("**Description courte**")
        st.write(res.get("short_description",""))
        st.markdown("**Tags Etsy**")
        st.code(", ".join(res.get("tags",[])), language=None)
        st.markdown("**Bloc prêt à copier**")
        st.text_area("", value=res.get("copy_paste_block",""), height=260)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="warn-box">⚠️ Important : pour Etsy, garde les images fidèles au produit réel. L’extraction AliExpress peut varier selon les pages et la protection anti-bot.</div>', unsafe_allow_html=True)
