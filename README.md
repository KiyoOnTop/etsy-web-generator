# Etsy Product Listing Generator V6 - Interface Française

Interface en français, génération des fiches Etsy en anglais.

Fonctions :
- URL AliExpress avec extraction automatique si possible
- ScraperAPI optionnel pour contourner les blocages AliExpress
- Prompt modifiable à la main
- Catégories prédéfinies
- Mots-clés SEO personnalisés
- Fiche concurrente pour inspiration
- Génération en anglais : titre, description, 13 tags, prix conseillé

## Secrets Streamlit recommandés

Dans Streamlit Cloud > Settings > Secrets :

```toml
OPENAI_API_KEY = "ta_cle_openai"
SCRAPERAPI_KEY = "ta_cle_scraperapi"
```
