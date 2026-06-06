# Etsy Product Listing Generator V23

Version Streamlit en français avec extraction AliExpress, génération fiche Etsy en anglais, extraction photos, et génération photos premium.

Nouveauté V23 : options par photo sélectionnée.

Pour chaque photo AliExpress, tu peux choisir :
- utiliser ou non la photo ;
- le nombre de versions à générer ;
- la vue à respecter : automatique, face, dos, latérale, gros plan, flat lay.

Déploiement :
1. Envoyer `app.py`, `requirements.txt`, `README.md` sur GitHub.
2. Commit changes.
3. Streamlit se met à jour automatiquement.

Secrets Streamlit recommandés :
```toml
OPENAI_API_KEY = "ta_cle_openai"
SCRAPERAPI_KEY = "ta_cle_scraperapi"
```
