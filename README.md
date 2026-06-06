# Etsy SEO Generator V14

Interface française, génération Etsy en anglais, extraction AliExpress, prompts modifiables, photos extraites et génération d'images carrées 1:1 via l'API OpenAI.

## Déploiement Streamlit

Fichiers à envoyer sur GitHub :
- app.py
- requirements.txt
- README.md

## Secrets Streamlit recommandés

```toml
OPENAI_API_KEY = "ta_cle_openai"
SCRAPERAPI_KEY = "ta_cle_scraperapi"
```

## Notes importantes

- L'extraction AliExpress peut échouer si AliExpress bloque la page.
- ScraperAPI améliore l'extraction.
- Les images générées doivent rester fidèles au vrai produit pour éviter une fiche trompeuse.
- Assure-toi d'avoir les droits d'utilisation nécessaires pour les images source.
