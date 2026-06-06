import json
import re
import requests
from bs4 import BeautifulSoup
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Etsy Corset Listing Generator V4", page_icon="🛍️", layout="wide")

st.title("🛍️ Etsy Corset Product Listing Generator V4")
st.caption("Paste an AliExpress URL, extract product info when possible, then generate an English SEO Etsy listing specialized for corsets.")

# ---------- Helpers ----------
def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

OPENAI_SECRET = get_secret("OPENAI_API_KEY", "")
SCRAPERAPI_SECRET = get_secret("SCRAPERAPI_KEY", "")

with st.sidebar:
    st.header("Settings")
    openai_key = st.text_input("OpenAI API key", value=OPENAI_SECRET, type="password")
    scraperapi_key = st.text_input("ScraperAPI key optional", value=SCRAPERAPI_SECRET, type="password")
    st.caption("ScraperAPI helps read AliExpress pages when direct extraction is blocked.")
    margin = st.slider("Target profit margin %", 20, 90, 45)
    shipping = st.number_input("Estimated shipping cost", min_value=0.0, value=0.0, step=0.5)
    fees_pct = st.slider("Estimated Etsy + payment fees %", 5, 30, 12)
    currency = st.selectbox("Currency", ["USD", "EUR", "GBP", "CAD", "AUD"], index=1)


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
            return None, f"HTTP error {r.status_code}"
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
    for c in desc_candidates[:5]:
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


def safe_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return []


def generate_listing(api_key, data, niche, tone, cost_price, competitor_info):
    client = OpenAI(api_key=api_key)
    sell_price = recommended_price(cost_price, shipping, margin, fees_pct)
    prompt = f"""
You are an Etsy SEO expert and high-converting product listing copywriter.

I run an Etsy dropshipping store specialized in corsets.

You will receive:
- An AliExpress product title
- An AliExpress product description
- Optional keywords or competitor information

Your mission is to generate a complete Etsy product listing including:

1. An SEO-optimized Etsy title that is highly relevant to search keywords while remaining natural and readable.
2. An SEO-optimized product description written in fluent English, persuasive and pleasant to read, with a warm tone and a few relevant emojis, but not too many.
3. Exactly 13 Etsy tags optimized for Etsy SEO.

Important rules:
- Output everything in English.
- Never copy competitor text word-for-word.
- Keep the style natural, persuasive and conversion-focused.
- Avoid keyword stuffing.
- Tags must be maximum 20 characters each.
- Tags must be provided on a single line separated by commas.
- Use the strongest Etsy keywords naturally in the title and first paragraph.
- Focus on corsets, waist trainers, gothic corsets, renaissance corsets, burlesque fashion, shapewear and alternative fashion whenever relevant.
- Do NOT claim handmade unless the supplier data clearly says handmade.
- Do NOT make medical, permanent body transformation, or unrealistic slimming claims.
- Keep the SEO title under 140 characters.

Supplier title:
{data.get('title','')}

Supplier description:
{data.get('description','')}

Supplier price:
{data.get('price','')}

Target buyer / niche:
{niche}

Tone:
{tone}

Optional keywords or competitor information:
{competitor_info}

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
    result = json.loads(response.choices[0].message.content)
    result["tags"] = safe_list(result.get("tags", []))[:13]
    result["keywords"] = safe_list(result.get("keywords", []))
    result["suggested_price"] = result.get("suggested_price", f"{sell_price} {currency}")
    return result

# ---------- UI ----------
left, right = st.columns([1.05, 0.95])
with left:
    st.subheader("Product source")
    url = st.text_input("AliExpress product URL")
    colA, colB = st.columns(2)
    extracted = st.session_state.get("extracted", {"title": "", "description": "", "price": ""})

    with colA:
        if st.button("Extract from AliExpress URL", type="primary"):
            if not url:
                st.warning("Paste an AliExpress URL first.")
            else:
                with st.spinner("Reading product page..."):
                    html, err = fetch_url(url, scraperapi_key)
                    if err or not html:
                        st.error(f"Extraction failed: {err}. Paste product details manually below.")
                    else:
                        data = extract_product_from_html(html)
                        if not data.get("title") and not data.get("description"):
                            st.warning("AliExpress blocked or hid the useful data. Add a ScraperAPI key or paste manually.")
                        else:
                            st.session_state["extracted"] = data
                            st.success("Product information extracted. Review/edit below.")
                            st.rerun()
    with colB:
        if st.button("Clear fields"):
            st.session_state["extracted"] = {"title": "", "description": "", "price": ""}
            st.session_state.pop("result", None)
            st.rerun()

    title = st.text_input("Supplier product title", value=extracted.get("title", ""))
    description = st.text_area("Supplier product description", value=extracted.get("description", ""), height=220)
    supplier_price = st.text_input("Supplier price detected optional", value=extracted.get("price", ""))
    cost_price = st.number_input("Product cost price", min_value=0.0, value=5.0, step=0.5)
    niche = st.text_input("Target buyer / niche", value="corset, gothic fashion, waist trainer", placeholder="Example: gothic corset, renaissance outfit, burlesque fashion")
    tone = st.selectbox("Tone", ["Premium and trustworthy", "Warm and emotional", "Minimalist and modern", "Gift-focused", "Luxury boutique"], index=0)
    competitor_info = st.text_area("Optional keywords or competitor listing", placeholder="Paste competitor title, keywords, or notes here. The app will take inspiration without copying.", height=120)

    if st.button("Generate Etsy listing", type="primary"):
        if not openai_key:
            st.error("Add your OpenAI API key in the sidebar first.")
        elif not title and not description:
            st.error("Extract product info from URL or paste title/description manually.")
        else:
            with st.spinner("Generating English Etsy SEO listing for corsets..."):
                try:
                    result = generate_listing(openai_key, {"title": title, "description": description, "price": supplier_price}, niche, tone, cost_price, competitor_info)
                    st.session_state["result"] = result
                except Exception as e:
                    st.error(f"Generation failed: {e}")

with right:
    st.subheader("Generated Etsy listing")
    result = st.session_state.get("result")
    if not result:
        st.info("Your generated corset listing will appear here.")
    else:
        st.markdown("### SEO Title")
        st.code(result.get("seo_title", ""), language=None)
        st.markdown("### Short description")
        st.write(result.get("short_description", ""))
        st.markdown("### Full description")
        st.write(result.get("full_description", ""))
        st.markdown("### Bullet points")
        for b in safe_list(result.get("bullet_points", [])):
            st.write(f"• {b}")
        st.markdown("### 13 Etsy tags")
        st.code(", ".join(safe_list(result.get("tags", []))[:13]), language=None)
        st.markdown("### Suggested price")
        st.code(str(result.get("suggested_price", "")), language=None)
        st.markdown("### Copy-paste block")
        st.text_area("Ready to copy", value=result.get("copy_paste_block", ""), height=300)
