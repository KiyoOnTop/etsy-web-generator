# Etsy Product Listing Generator V18

Version avec génération de photos plus fidèle :

- Interface française.
- Fiches Etsy générées en anglais.
- Extraction AliExpress + ScraperAPI.
- Photos AliExpress extraites.
- Sélection des photos.
- Choix de la vue pour chaque photo : automatique, face, dos, latérale, gros plan, flat lay.
- Prompt photo personnalisable.
- Styles photo : Luxury Interior, Fashion Editorial, Romantic Boutique, Clean Ecommerce.
- Mode de modification : changer fond/décor/mannequin, changer seulement fond/décor, retouche légère.
- Règles renforcées pour garder le produit identique.

## Déploiement Streamlit

Uploader sur GitHub :

- app.py
- requirements.txt
- README.md

Puis laisser Streamlit redéployer.

## Secrets Streamlit recommandés

```toml
OPENAI_API_KEY = "ta_cle_openai"
SCRAPERAPI_KEY = "ta_cle_scraperapi"
```
