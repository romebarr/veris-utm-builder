# UTM Builder — Veris

App en Streamlit para construir URLs de campaña con la nomenclatura estándar de Veris.

- `utm_source` = plataforma (`meta`, `tiktok`, `mailing`, `whatsapp`, `sms`, `push`), no la red suelta
- `utm_medium` = `paid` para pauta, `organic` para social orgánico, y `email` / `chat` / `sms` / `push`
- `utm_campaign` = `plataforma_objetivo_producto` (+ `_geo` `_periodo` opcionales)
- `utm_term` = conjunto de anuncios (audiencia) — solo canales con jerarquía (Meta / TikTok)
- `utm_content` = anuncio / creatividad (aquí se marca `ig-` vs `fb-`)

### Meta con macros dinámicos (opcional)

Toggle **"Usar macros dinámicos de Meta"** en la barra lateral. Modelo híbrido: el builder
controla la campaña (estable y limpia) y Meta rellena los niveles de abajo en el momento del clic.

| Parámetro | Valor | Origen |
|---|---|---|
| `utm_source` / `utm_medium` | `meta` / `paid` | fijo |
| `utm_campaign` | `meta_conversion_citas_uio` | builder |
| `utm_term` | `{{adset.name}}` | macro |
| `utm_content` | `{{site_source_name}}-{{ad.name}}` | macro (`fb` / `ig` / `an` / `msg`) |
| `utm_id` | `{{campaign.id}}` | macro — cruce de costo y sobrevive renombrados |

La app entrega dos bloques: la URL del sitio web **limpia** y el string de parámetros. El string va
en *Seguimiento → Parámetros de URL*, **a nivel anuncio** — nunca en los dos sitios a la vez, o los
UTMs se duplican.

Antes de activarlo: los conjuntos y anuncios deben estar nombrados limpios dentro de Meta, porque
el macro copia el nombre tal cual (espacios, mayúsculas y emojis incluidos).

### Google Ads

Sin UTM manual: el auto-tagging (`gclid`) lleva los nombres a GA4. La app entrega los nombres a usar
dentro de la cuenta:

| Nivel | Estructura | Ejemplo |
|---|---|---|
| Campaña | `google_tipo_[objetivo]_producto_[periodo]` | `google_search_conversion_cardiologia_2026-q3` |
| Grupo de anuncios — search | `tema_intencion_concordancia` | `cardiologia_generico_exacta` |
| Grupo de recursos — pmax / shopping | `producto_publico` | `paquetes-preventivos_general` |
| Grupo de anuncios — display / video / gdemand | `audiencia_formato` | `remarketing-30d_video-15s` |

A cualquier grupo se le puede añadir `_geo` al final (`cardiologia_generico_exacta_uio`).

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
- `INTENCIONES`, `CONCORDANCIAS`, `AUDIENCIAS`, `FORMATOS`, `PUBLICOS` — bloques del grupo de anuncios
- `OBJETIVOS`, `PRODUCTOS`, `GEOS` — listas desplegables (siempre queda la opción "otro…" para texto libre)
