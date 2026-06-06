import os
import re
import json
from urllib.parse import urlparse

import requests
import streamlit as st
from bs4 import BeautifulSoup
from openai import OpenAI

st.set_page_config(page_title="Etsy Product Listing Generator", page_icon="🛍️", layout="wide")

st.title("🛍️ Etsy Product Listing Generator")
st.caption("Paste an AliExpress product link or supplier information, then generate an English Etsy SEO listing.")


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_aliexpress_data(url: str) -> dict:
    """Best-effort extractor. AliExpress is often protected/dynamic, so this may return partial data."""
    if not url:
        return {"title": "", "description": "", "error": "Please paste a product URL."}

    parsed = urlparse(url)
    if not parsed.scheme.startswith("http") or "aliexpress" not in parsed.netloc.lower():
        return {"title": "", "description": "", "error": "Please paste a valid AliExpress product URL."}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        return {
            "title": "",
            "description": "",
            "error": f"Could not read this AliExpress page automatically. Paste the title/description manually below. Details: {exc}",
        }

    soup = BeautifulSoup(response.text, "html.parser")

    title = ""
    description = ""

    # Try OpenGraph / Twitter metadata first.
    for selector in [
        ("meta", {"property": "og:title"}),
        ("meta", {"name": "twitter:title"}),
    ]:
        tag = soup.find(*selector)
        if tag and tag.get("content"):
            title = clean_text(tag.get("content"))
            break

    for selector in [
        ("meta", {"property": "og:description"}),
        ("meta", {"name": "description"}),
        ("meta", {"name": "twitter:description"}),
    ]:
        tag = soup.find(*selector)
        if tag and tag.get("content"):
            description = clean_text(tag.get("content"))
            break

    # Fallback to page title.
    if not title and soup.title:
        title = clean_text(soup.title.get_text())

    # Try JSON-LD product data.
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict) and item.get("@type") in ["Product", "product"]:
                    title = title or clean_text(item.get("name", ""))
                    description = description or clean_text(item.get("description", ""))
        except Exception:
            pass

    if not title and not description:
        return {
            "title": "",
            "description": "",
            "error": "AliExpress blocked automatic reading for this page. Paste the supplier title/description manually below.",
        }

    return {"title": title, "description": description, "error": ""}


with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("OpenAI API key", type="password", value=os.getenv("OPENAI_API_KEY", ""))
    target_margin = st.slider("Target profit margin", 20, 80, 45)
    shipping_cost = st.number_input("Estimated shipping cost", min_value=0.0, value=0.0, step=0.5)
    platform_fees = st.slider("Estimated Etsy + payment fees", 5, 25, 12)
    st.info("Your API key is not stored by this app. For deployment, use Streamlit Secrets instead of typing it every time.")

if "product_title" not in st.session_state:
    st.session_state.product_title = ""
if "product_description" not in st.session_state:
    st.session_state.product_description = ""

col1, col2 = st.columns(2)

with col1:
    st.subheader("Product input")
    product_url = st.text_input("AliExpress product URL", placeholder="https://www.aliexpress.com/item/...")

    if st.button("Extract title/description from URL"):
        with st.spinner("Reading AliExpress page..."):
            extracted = extract_aliexpress_data(product_url)
        if extracted.get("error"):
            st.warning(extracted["error"])
        if extracted.get("title"):
            st.session_state.product_title = extracted["title"]
        if extracted.get("description"):
            st.session_state.product_description = extracted["description"]
        if extracted.get("title") or extracted.get("description"):
            st.success("Product data extracted. You can edit it before generating.")

    product_title = st.text_input("Supplier product title", key="product_title")
    product_description = st.text_area("Supplier product description", height=220, key="product_description")
    cost_price = st.number_input("Product cost price", min_value=0.0, value=5.0, step=0.5)
    audience = st.text_input("Target buyer / niche", placeholder="Example: women gift, home decor, pet lovers")
    style = st.selectbox("Tone", ["Premium and trustworthy", "Warm and friendly", "Minimalist", "Gift-focused"])
    generate = st.button("Generate Etsy listing", type="primary")

with col2:
    st.subheader("Generated Etsy listing")
    output_box = st.empty()


def calculate_price(cost: float, shipping: float, margin: int, fees: int) -> float:
    base = cost + shipping
    denominator = 1 - (margin / 100) - (fees / 100)
    if denominator <= 0:
        return round(base * 2.5, 2)
    return round(base / denominator, 2)


def build_prompt():
    suggested_price = calculate_price(cost_price, shipping_cost, target_margin, platform_fees)
    return f"""
You are an expert Etsy SEO copywriter.
Create a high-converting Etsy product listing in ENGLISH.

Important rules:
- Do NOT copy the AliExpress title word-for-word.
- Make the title keyword-rich, natural, and optimized for Etsy search.
- Make the listing sound premium, clear, and trustworthy.
- Avoid false handmade claims.
- Avoid trademarked brand names unless provided by the seller.
- Keep the Etsy title under 140 characters.
- Provide exactly 13 Etsy tags, each under 20 characters if possible.
- The user will manually copy/paste the result into Etsy.

AliExpress URL:
{product_url}

Supplier title:
{product_title}

Supplier description:
{product_description}

Target buyer / niche:
{audience}

Tone:
{style}

Cost price: {cost_price}
Estimated shipping: {shipping_cost}
Target margin: {target_margin}%
Estimated fees: {platform_fees}%
Suggested selling price: {suggested_price}

Return valid JSON only with these fields:
- etsy_title
- short_description
- full_description
- bullet_points: array of 5 bullets
- tags: array of exactly 13 tags
- seo_keywords: array of 10 keywords
- category_suggestion
- suggested_price
- copy_paste_block
"""

if generate:
    if not api_key:
        st.error("Please enter your OpenAI API key in the sidebar.")
    elif not product_title and not product_description and not product_url:
        st.error("Please paste an AliExpress URL or add a product title/description.")
    else:
        try:
            # If user pasted only a URL, try to extract before generating.
            if product_url and not product_title and not product_description:
                extracted = extract_aliexpress_data(product_url)
                if extracted.get("title"):
                    product_title = extracted["title"]
                    st.session_state.product_title = product_title
                if extracted.get("description"):
                    product_description = extracted["description"]
                    st.session_state.product_description = product_description

            client = OpenAI(api_key=api_key)
            with st.spinner("Generating your Etsy listing..."):
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You write excellent English Etsy listings and return valid JSON only."},
                        {"role": "user", "content": build_prompt()},
                    ],
                    temperature=0.7,
                )
            raw = response.choices[0].message.content
            data = json.loads(raw)
            output_box.json(data)
            st.download_button(
                "Download JSON",
                data=json.dumps(data, ensure_ascii=False, indent=2),
                file_name="etsy_listing.json",
                mime="application/json",
            )
        except json.JSONDecodeError:
            st.warning("The AI response was not valid JSON. Here is the raw result:")
            st.code(raw)
        except Exception as e:
            st.error(f"Error: {e}")

st.divider()
st.subheader("How to use")
st.write("1. Paste an AliExpress product URL. 2. Click Extract. 3. Edit the extracted text if needed. 4. Click Generate. 5. Copy the English result into Etsy.")
st.warning("AliExpress pages can block automatic reading. If extraction fails, copy/paste the supplier title and description manually, then generate.")
st.warning("Reminder: Etsy has strict rules about reselling and dropshipping. Use this tool as a writing assistant and verify that your products comply with Etsy policies.")
