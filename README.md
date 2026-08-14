# UTM Builder — Veris

App en Streamlit para construir URLs de campaña con la nomenclatura estándar de Veris.

- `utm_source` = plataforma (`meta`, `tiktok`, `mailing`, `whatsapp`, `sms`, `push`), no la red suelta
- `utm_medium` = `paid` para pauta, `organic` para social orgánico, y `email` / `chat` / `sms` / `push`
- `utm_campaign` = `plataforma_objetivo_producto` (+ `_geo` `_periodo` opcionales)
- `utm_term` = conjunto de anuncios (audiencia) — solo canales con jerarquía (Meta / TikTok)
- `utm_content` = anuncio / creatividad (aquí se marca `ig-` vs `fb-`)
- **Google Ads**: sin UTM manual (auto-tagging con `gclid`); la app entrega el nombre de campaña `google_tipo_producto`

Repo: https://github.com/romebarr/veris-utm-builder

## Correr en local

```bash
git clone https://github.com/romebarr/veris-utm-builder.git
cd veris-utm-builder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Abre http://localhost:8501

## Desplegar en Streamlit Community Cloud

1. Entra a https://share.streamlit.io e inicia sesión con la cuenta de GitHub
   dueña del repo (`romebarr`).
2. **Create app** → *Deploy a public app from GitHub*.
3. Configura:
   - **Repository**: `romebarr/veris-utm-builder`
   - **Branch**: `main`
   - **Main file path**: `app.py`
   - **App URL**: p. ej. `veris-utm-builder` → `https://veris-utm-builder.streamlit.app`
   - *Advanced settings* → **Python version**: 3.12
4. **Deploy**. Tarda ~2 min en instalar `requirements.txt`.

Atajo con todo prellenado:
https://share.streamlit.io/deploy?repository=romebarr/veris-utm-builder&branch=main&mainModule=app.py

No hace falta ningún secret. Cada `git push` a `main` redespliega la app sola.

### Restringir acceso
En la app desplegada: **Settings → Sharing** → *Who can view this app* → limita a
los correos del equipo de marketing.

## Editar catálogos

En `app.py`, arriba del todo:

- `CHANNELS` — canales con su `utm_source` / `utm_medium` fijos
- `GOOGLE_TYPES` — tipos de campaña de Google Ads
- `OBJETIVOS`, `PRODUCTOS`, `GEOS` — listas desplegables (siempre queda la opción "otro…" para texto libre)
