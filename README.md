# Etsy Listing Generator V5

A Streamlit app that generates English Etsy product listings from AliExpress product data.

## V5 features

- AliExpress URL extraction when possible
- Optional ScraperAPI support
- OpenAI-powered English SEO title, description and tags
- Editable prompt area directly inside the website
- Multiple preset categories:
  - Corsets
  - Jewelry
  - Home Decor
  - Pet Products
  - Beauty Accessories
  - Clothing / Fashion
  - Custom / Manual prompt
- Optional SEO keywords
- Optional competitor inspiration field

## Streamlit secrets

Add these in Streamlit Cloud secrets:

```toml
OPENAI_API_KEY = "your_openai_key_here"
SCRAPERAPI_KEY = "your_scraperapi_key_here"
```

ScraperAPI is optional, but helps with AliExpress extraction.
