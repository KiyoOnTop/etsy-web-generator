# Etsy Product Listing Generator

A simple web app for generating English Etsy product listings from supplier product information.

## Local use

1. Install Python 3.11 or newer.
2. Open a terminal in this folder.
3. Run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Create a GitHub account.
2. Create a new repository.
3. Upload `app.py`, `requirements.txt`, and this `README.md`.
4. Go to Streamlit Community Cloud.
5. Connect your GitHub repository.
6. In Streamlit secrets, add:

```toml
OPENAI_API_KEY = "your_api_key_here"
```

Then open your app link.

## Use

Paste the AliExpress product title and description, set your price information, then click Generate.
The output is in English and ready to copy/paste manually into Etsy.
