# Etsy Web Generator V25

Interface française, génération de fiche Etsy en anglais, extraction AliExpress, photos avec prompt par image.

## Installation Streamlit
Uploader sur GitHub :
- app.py
- requirements.txt
- README.md

Puis Streamlit redéploie automatiquement.

## Clés nécessaires
Dans la sidebar ou Streamlit Secrets :

OPENAI_API_KEY = "votre_cle_openai"
SCRAPERAPI_KEY = "votre_cle_scraperapi"

## Photos IA
Chaque photo extraite a ses propres réglages :
- utiliser ou non
- vue : face, dos, profil, détail
- style
- nombre de variantes
- prompt personnalisé
