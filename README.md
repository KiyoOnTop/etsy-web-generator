# Etsy Corset Listing Generator V4

Streamlit app for generating English Etsy SEO product listings specialized for corsets.

## Features
- AliExpress URL extraction when possible
- Optional ScraperAPI support for blocked pages
- English Etsy SEO title
- Warm conversion-focused description with a few emojis
- Exactly 13 Etsy tags
- Optional competitor/keyword input
- Suggested price calculation

## Streamlit secrets
Add these in Streamlit Cloud secrets:

```toml
OPENAI_API_KEY = "your_openai_key_here"
SCRAPERAPI_KEY = "your_scraperapi_key_here"
```

SCRAPERAPI_KEY is optional, but useful for AliExpress extraction.
