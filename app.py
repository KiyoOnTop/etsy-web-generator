import json
import re
import requests
from bs4 import BeautifulSoup
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Etsy Listing Generator V5", page_icon="🛍️", layout="wide")

st.title("🛍️ Etsy Product Listing Generator V5")
st.caption("Paste an AliExpress URL, choose a product category or edit the prompt manually, then generate an English SEO Etsy listing.")

# ---------- Helpers ----------
def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

OPENAI_SECRET = get_secret("OPENAI_API_KEY", "")
SCRAPERAPI_SECRET = get_secret("SCRAPERAPI_KEY", "")

CATEGORY_PROMPTS = {
    "Corsets": """I run an Etsy dropshipping store specialized in corsets. Focus on buyers looking for corsets, waist trainers, gothic corsets, renaissance corsets, burlesque fashion, shapewear and alternative fashion when relevant.""",
    "Jewelry": """I run an Etsy dropshipping store specialized in jewelry and accessories. Focus on giftable jewelry, elegant accessories, minimalist jewelry, statement pieces, birthday gifts and everyday fashion accessories when relevant.""",
    "Home Decor": """I run an Etsy dropshipping store specialized in home decor. Focus on cozy decor, aesthetic room decor, modern home accessories, housewarming gifts, minimalist decor and stylish interior decoration when relevant.""",
    "Pet Products": """I run an Etsy dropshipping store specialized in pet products. Focus on pet owners, dog lovers, cat lovers, practical pet accessories, cute pet gifts and comfort-focused products when relevant.""",
    "Beauty Accessories": """I run an Etsy dropshipping store specialized in beauty accessories. Focus on beauty lovers, skincare routines, makeup organization, self-care gifts, practical beauty tools and elegant bathroom accessories when relevant.""",
    "Clothing / Fashion": """I run an Etsy dropshipping store specialized in fashion and clothing. Focus on outfit styling, trend-focused buyers, everyday wear, statement fashion pieces, gifts and aesthetic clothing when relevant.""",
    "Custom / Manual prompt": """Write your own store niche, target audience, SEO angle and style instructions here.""",
}

DEFAULT_RULES = """You are an Etsy SEO expert and high-converting product listing copywriter.

Your mission is to generate a complete Etsy product listing including:
1. An SEO-optimized Etsy title that is highly relevant to search keywords while remaining natural and readable.
2. An SEO-optimized product description written in fluent English, persuasive and pleasant to read, with a warm tone and a few relevant emojis (not excessive).
3. Exactly 13 Etsy tags optimized for Etsy SEO.

Important rules:
- Output everything in English.
- Do NOT claim handmade unless explicitly stated by the user.
- Never copy competitor text word-for-word.
- Keep the style natural, persuasive and conversion-focused.
- Avoid keyword stuffing.
- Keep the Etsy title under 140 characters.
- Tags must be maximum 20 characters each.
- Tags must be provided on a single line separated by commas.
- Use the strongest Etsy keywords naturally in the title and first paragraph.
- Make the listing ready to copy and paste into Etsy."""

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
            r = requests.get(api_url, params={"api_key": scraper_key, "url": url, "render": "true", "country_code": "us"}, timeout=60)
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
        title = max([c.encode('utf-8').decode('unicode_escape', errors='ignore') for c in candidates], key=len)
    desc_candidates = re.findall(r'"(?:description|productDescription|seoDescription)"\s*:\s*"(.*?)"', text)
    for c in desc_candidates[:5]:
        desc_parts.append(c.encode('utf-8').decode('unicode_escape', errors='ignore'))
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


def generate_listing(api_key, data, niche, tone, cost_price, category, custom_prompt, competitor_info, keywords):
    client = OpenAI(api_key=api_key)
    sell_price = recommended_price(cost_price, shipping, margin, fees_pct)

    prompt = f"""
{DEFAULT_RULES}

Selected product category:
{category}

Category / custom instructions:
{custom_prompt}

Additional target buyer / niche:
{niche}

Optional SEO keywords to prioritize:
{keywords}

Optional competitor inspiration. Use it for ideas only, never copy it word-for-word:
{competitor_info}

Tone:
{tone}

Supplier title:
{data.get('title','')}

Supplier description:
{data.get('description','')}

Supplier price:
{data.get('price','')}

Cost price:
{cost_price} {currency}

Suggested selling price:
{sell_price} {currency}

Return ONLY valid JSON with these keys:
seo_title, short_description, full_description, bullet_points, tags, tags_one_line, keywords, category_suggestion, suggested_price, copy_paste_block
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
    description = st.text_area("Supplier product description", value=extracted.get("description", ""), height=180)
    supplier_price = st.text_input("Supplier price detected optional", value=extracted.get("price", ""))
    cost_price = st.number_input("Product cost price", min_value=0.0, value=5.0, step=0.5)

    st.subheader("Prompt / category settings")
    selected_category = st.selectbox("Product category", list(CATEGORY_PROMPTS.keys()), index=0)

    if "last_category" not in st.session_state:
        st.session_state["last_category"] = selected_category
        st.session_state["custom_prompt"] = CATEGORY_PROMPTS[selected_category]
    elif st.session_state["last_category"] != selected_category:
        st.session_state["last_category"] = selected_category
        st.session_state["custom_prompt"] = CATEGORY_PROMPTS[selected_category]

    custom_prompt = st.text_area(
        "Editable prompt instructions",
        value=st.session_state.get("custom_prompt", CATEGORY_PROMPTS[selected_category]),
        height=180,
        help="You can edit this manually for any niche: corsets, jewelry, home decor, pet products, etc.",
    )
    st.session_state["custom_prompt"] = custom_prompt

    colP1, colP2 = st.columns(2)
    with colP1:
        if st.button("Reset prompt for this category"):
            st.session_state["custom_prompt"] = CATEGORY_PROMPTS[selected_category]
            st.rerun()
    with colP2:
        if st.button("Use blank custom prompt"):
            st.session_state["custom_prompt"] = ""
            st.rerun()

    niche = st.text_input("Target buyer / niche", placeholder="Example: gothic fashion, women gift, home decor, pet lovers")
    keywords = st.text_input("Optional SEO keywords", placeholder="Example: gothic corset, waist trainer, renaissance outfit")
    competitor_info = st.text_area("Optional competitor listing or notes", height=100, placeholder="Paste competitor title/description here if you want inspiration. Do not copy competitors directly.")
    tone = st.selectbox("Tone", ["Premium and trustworthy", "Warm and emotional", "Minimalist and modern", "Gift-focused", "Luxury boutique"])

    if st.button("Generate Etsy listing", type="primary"):
        if not openai_key:
            st.error("Add your OpenAI API key in the sidebar first.")
        elif not title and not description:
            st.error("Extract product info from URL or paste title/description manually.")
        else:
            with st.spinner("Generating English Etsy SEO listing..."):
                try:
                    result = generate_listing(
                        openai_key,
                        {"title": title, "description": description, "price": supplier_price},
                        niche,
                        tone,
                        cost_price,
                        selected_category,
                        custom_prompt,
                        competitor_info,
                        keywords,
                    )
                    st.session_state["result"] = result
                except Exception as e:
                    st.error(f"Generation failed: {e}")

with right:
    st.subheader("Generated Etsy listing")
    result = st.session_state.get("result")
    if not result:
        st.info("Your generated listing will appear here.")
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
        tags_one_line = result.get("tags_one_line", ", ".join(tags if isinstance(tags, list) else []))
        st.code(tags_one_line, language=None)
        st.markdown("### Suggested price")
        st.code(str(result.get("suggested_price", "")), language=None)
        st.markdown("### Copy-paste block")
        st.text_area("Ready to copy", value=result.get("copy_paste_block", ""), height=300)
