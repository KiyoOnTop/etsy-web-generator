import os
import json
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Etsy Product Listing Generator", page_icon="🛍️", layout="wide")

st.title("🛍️ Etsy Product Listing Generator")
st.caption("Generate English Etsy product titles, descriptions, tags, and pricing from AliExpress product information.")

with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("OpenAI API key", type="password", value=os.getenv("OPENAI_API_KEY", ""))
    target_margin = st.slider("Target profit margin", 20, 80, 45)
    shipping_cost = st.number_input("Estimated shipping cost", min_value=0.0, value=0.0, step=0.5)
    platform_fees = st.slider("Estimated Etsy + payment fees", 5, 25, 12)
    st.info("Your API key is not stored by this app. For deployment, use Streamlit Secrets instead of typing it every time.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Product input")
    product_title = st.text_input("AliExpress product title")
    product_description = st.text_area("AliExpress product description", height=220)
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
- Make the listing sound natural, premium, and trustworthy.
- Avoid false handmade claims.
- Avoid trademarked brand names unless provided by the seller.
- Keep the Etsy title under 140 characters.
- Provide exactly 13 Etsy tags, each under 20 characters if possible.
- The user will manually copy/paste the result into Etsy.

Product title from supplier:
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
    elif not product_title or not product_description:
        st.error("Please add at least a product title and description.")
    else:
        try:
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
st.write("1. Paste the AliExpress product title and description. 2. Add your cost price. 3. Click Generate. 4. Copy the English result into Etsy.")
st.warning("Reminder: Etsy has strict rules about reselling and dropshipping. Use this tool as a writing assistant and verify that your products comply with Etsy policies.")
