# UTM Builder — Veris

App en Streamlit para construir URLs de campaña con la nomenclatura estándar de Veris.

- `utm_campaign` = `plataforma_objetivo_producto` (+ `_geo` `_periodo` opcionales)
- `utm_term` = conjunto de anuncios (audiencia) — solo canales con jerarquía (Meta / TikTok)
- `utm_content` = anuncio / creatividad
- **Google Ads**: sin UTM manual (auto-tagging con `gclid`); la app entrega el nombre de campaña `google_tipo_producto`

## Correr en local

```bash
cd utm-builder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Abre http://localhost:8501

> Streamlit aún no publica ruedas para Python 3.14. Usa Python 3.11–3.13
> (`brew install python@3.12` y luego `python3.12 -m venv .venv`).

## Desplegar en Streamlit Community Cloud

1. Sube esta carpeta a un repo de GitHub (público o privado).
2. Entra a https://share.streamlit.io → **Create app** → conecta el repo.
3. Configura:
   - **Main file path**: `utm-builder/app.py` (o `app.py` si el repo es solo esta carpeta)
   - **Python version**: 3.12
4. Deploy. La URL queda tipo `https://<app>.streamlit.app`.

Streamlit Cloud instala `requirements.txt` automáticamente. No hace falta ningún secret.

### Restringir acceso
En la app desplegada: **Settings → Sharing** → limita a los correos del equipo de marketing.

## Editar catálogos

En `app.py`, arriba del todo:

- `CHANNELS` — canales con su `utm_source` / `utm_medium` fijos
- `GOOGLE_TYPES` — tipos de campaña de Google Ads
- `OBJETIVOS`, `PRODUCTOS`, `GEOS` — listas desplegables (siempre queda la opción "otro…" para texto libre)
