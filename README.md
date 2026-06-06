# Etsy Product Listing Generator V3

This Streamlit web app generates English Etsy SEO product listings from AliExpress supplier information.

## V3 features

- Paste an AliExpress product URL
- Try direct extraction first
- Optional ScraperAPI support for more reliable AliExpress extraction
- Generate English SEO Etsy title, descriptions, 13 tags, category suggestion and price
- Manual fallback if AliExpress blocks extraction

## Streamlit Secrets

In Streamlit Cloud, open your app settings and add:

```toml
OPENAI_API_KEY = "your_openai_key_here"
SCRAPERAPI_KEY = "your_scraperapi_key_here" # optional
```

You can also type the keys in the sidebar while using the app.

## Main file

`app.py`
