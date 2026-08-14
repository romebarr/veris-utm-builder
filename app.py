"""
UTM Builder — Veris (v1.2)
Nomenclatura estándar para campañas: Meta, TikTok, Google, mail, WhatsApp, SMS, push.

- utm_source   = plataforma (meta, tiktok, mailing, whatsapp, sms, push)
- utm_medium   = paid para pauta; email / chat / sms / push para los directos
- utm_campaign = plataforma_objetivo_producto  (+ _geo _periodo opcionales)
- utm_term     = conjunto de anuncios (audiencia)   -> solo canales con jerarquía (Meta/TikTok)
- utm_content  = anuncio (creatividad); en Meta marca ig- / fb-
- Google Ads   = sin UTM manual (auto-tagging/gclid). Se nombran dentro de la cuenta:
                 campaña      google_tipo_[objetivo]_producto_[periodo]
                 grupo        tema_intencion_concordancia   (search)
                              producto_publico               (pmax/shopping)
                              audiencia_formato              (display/video/gdemand)

Ejecutar local:  streamlit run app.py
"""

import io
import csv
import re
import unicodedata
from typing import Dict, List, Tuple
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, quote

import streamlit as st


# ----------------------------------------------------------------------------
# Catálogos
# ----------------------------------------------------------------------------
DEFAULT_BASE_URL = "https://www.veris.com.ec/"
ALLOWED_HOST_SUFFIX = "veris.com.ec"

# Cada canal fija source + medium (según la nomenclatura de Veris).
# hierarchy=True -> el canal tiene conjunto de anuncios + anuncio (utm_term/utm_content).
CHANNELS: Dict[str, Dict] = {
    "Meta (pago)":                 {"source": "meta",      "medium": "paid",        "plataforma": "meta",     "hierarchy": True},
    "TikTok (pago)":               {"source": "tiktok",    "medium": "paid",        "plataforma": "tiktok",   "hierarchy": True},
    "Google Ads":                  {"google": True,        "plataforma": "google"},
    "Email / Mailing":             {"source": "mailing",   "medium": "email",       "plataforma": "mail",     "hierarchy": False},
    "WhatsApp":                    {"source": "whatsapp",  "medium": "chat",        "plataforma": "whatsapp", "hierarchy": False},
    "SMS":                         {"source": "sms",       "medium": "sms",         "plataforma": "sms",      "hierarchy": False},
    "Push (web/app)":              {"source": "push",      "medium": "push",        "plataforma": "push",     "hierarchy": False},
    "Otro (personalizado)":        {"otro": True,          "plataforma": ""},
}

# Tipos de campaña de Google Ads (el auto-tagging trae el nombre a GA4).
GOOGLE_TYPES = ["search", "pmax", "gdemand", "display", "video", "shopping"]

# Cómo se arma el grupo de anuncios según el tipo de campaña.
#   search           -> tema_intencion_concordancia   (cardiologia_generico_exacta)
#   pmax / shopping  -> grupo de recursos: producto_publico
#   display/video/gd -> audiencia_formato
INTENCIONES = ["marca", "generico", "competencia", "sintoma", "precio", "ubicacion"]
CONCORDANCIAS = ["exacta", "frase", "amplia"]
AUDIENCIAS = ["inmarket-salud", "afinidad-salud", "remarketing-30d", "remarketing-90d",
              "similares", "datos-propios", "amplia"]
FORMATOS = ["video-15s", "video-30s", "video-6s", "display-responsive", "banner-estatico"]
PUBLICOS = ["general", "remarketing", "datos-propios", "empresas"]

OBJETIVOS = ["trafico", "conversion", "leads", "alcance", "remarketing", "awareness", "retencion"]
PRODUCTOS = [
    "paquetes-preventivos", "citas", "farmacia", "laboratorio", "imagenes",
    "chequeo-ejecutivo", "maternidad", "cardiologia", "pediatria", "odontologia",
    "empresas", "marca",
]
GEOS = ["nacional", "uio", "gye", "cue", "mta", "amb"]

OTRO = "➕ otro…"


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def slug(value: str) -> str:
    """minúsculas, sin tildes/ñ, espacios->'-', solo [a-z0-9._-]."""
    if not value:
        return ""
    value = value.strip().lower()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"[^a-z0-9._-]", "", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value


def pick(label: str, options: List[str], key: str, placeholder: str = "") -> str:
    """Selectbox con catálogo + opción libre. Devuelve el valor ya slugificado."""
    choice = st.selectbox(label, options=[""] + options + [OTRO], key=f"{key}_sel")
    if choice == OTRO:
        return slug(st.text_input(f"{label} (libre)", key=f"{key}_free", placeholder=placeholder))
    return slug(choice)


def build_campaign(plataforma: str, objetivo: str, producto: str,
                   geo: str = "", periodo: str = "") -> str:
    """plataforma_objetivo_producto (+ _geo _periodo opcionales)."""
    blocks = [slug(plataforma), slug(objetivo), slug(producto)]
    if any(not b for b in blocks):
        return ""
    if slug(geo):
        blocks.append(slug(geo))
    if slug(periodo):
        blocks.append(slug(periodo))
    return "_".join(blocks)


def join_blocks(*blocks: str) -> str:
    """Une bloques ya slugificados con '_', descartando vacíos."""
    return "_".join([b for b in (slug(x) for x in blocks) if b])


def build_google_campaign(tipo: str, producto: str, objetivo: str = "",
                          periodo: str = "") -> str:
    """google_tipo_[objetivo]_producto[_periodo] (nombre a usar dentro de Google Ads)."""
    if not slug(tipo) or not slug(producto):
        return ""
    return join_blocks("google", tipo, objetivo, producto, periodo)


def build_ad_group(*blocks: str) -> str:
    """Grupo de anuncios (o grupo de recursos en pmax/shopping).

    search           -> tema_intencion_concordancia   (cardiologia_generico_exacta)
    pmax / shopping  -> producto_publico              (paquetes-preventivos_general)
    display/video/gd -> audiencia_formato             (remarketing-30d_video-15s)
    El primer bloque es obligatorio; los vacíos se descartan.
    """
    if not blocks or not slug(blocks[0]):
        return ""
    return join_blocks(*blocks)


def build_params(source, medium, campaign, term, content) -> List[Tuple[str, str]]:
    pairs = [
        ("utm_source", source),
        ("utm_medium", medium),
        ("utm_campaign", campaign),
        ("utm_term", term),
        ("utm_content", content),
    ]
    return [(k, v) for k, v in pairs if v]


def append_query_params(url: str, params: List[Tuple[str, str]]) -> str:
    """Añade UTMs respetando query existente y fragmento (#), sin duplicar claves."""
    if not params:
        return url
    parts = urlsplit(url)
    existing = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                if k.lower() not in {k2 for k2, _ in params}]
    query = urlencode(existing + params, quote_via=quote, safe="-._~")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def url_issues(url: str) -> Tuple[List[str], List[str]]:
    """(errores, advertencias) sobre la URL base."""
    errors, warnings = [], []
    if not url:
        errors.append("La URL base es obligatoria.")
        return errors, warnings
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        errors.append("La URL base no es válida (debe empezar con https:// e incluir dominio).")
        return errors, warnings
    if parts.scheme == "http":
        warnings.append("Usa https:// en vez de http://.")
    host = parts.netloc.split("@")[-1].split(":")[0].lower()
    if not (host == ALLOWED_HOST_SUFFIX or host.endswith("." + ALLOWED_HOST_SUFFIX)):
        warnings.append(f"El destino no es de `{ALLOWED_HOST_SUFFIX}`. Confirma que sea intencional.")
    if any(k.lower().startswith("utm_") for k, _ in parse_qsl(parts.query, keep_blank_values=True)):
        warnings.append("La URL base ya trae parámetros `utm_*`: se reemplazan por los de abajo.")
    return errors, warnings


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
st.set_page_config(page_title="UTM Builder — Veris", page_icon="🔗", layout="centered")
st.title("🔗 UTM Builder — Veris")
st.caption("Construye URLs de campaña con nomenclatura estándar. Todo se normaliza a minúsculas, sin tildes ni espacios.")

if "historial" not in st.session_state:
    st.session_state.historial = []

with st.sidebar:
    st.header("Inputs")

    channel_name = st.selectbox("Canal", options=list(CHANNELS.keys()), key="channel")
    channel = CHANNELS[channel_name]
    is_google = channel.get("google", False)
    is_otro = channel.get("otro", False)
    has_hierarchy = channel.get("hierarchy", False)

    base_url = st.text_input(
        "URL base (landing en www.veris.com.ec)",
        value=DEFAULT_BASE_URL,
        key="base_url",
        help="Ej: https://www.veris.com.ec/paquetes  ·  /citas  ·  /farmacia",
    ).strip()

    # ---- source / medium ----
    if is_otro:
        st.subheader("Source / Medium (personalizado)")
        plataforma = slug(st.text_input("Plataforma (para utm_campaign)", key="otro_plat"))
        source = slug(st.text_input("utm_source", key="otro_source"))
        medium = slug(st.text_input("utm_medium", key="otro_medium"))
    elif is_google:
        plataforma, source, medium = "google", "", ""
        st.info("Google Ads: auto-tagging (gclid) activo. **No** se agregan UTMs manuales; se nombra la campaña.")
    else:
        plataforma = channel["plataforma"]
        source = channel["source"]
        medium = channel["medium"]
        st.markdown(f"**utm_source:** `{source}`  ·  **utm_medium:** `{medium}`")

    st.divider()

    # ---- campaign ----
    st.subheader("utm_campaign")
    ad_group = ""
    if is_google:
        gtipo = st.selectbox("Tipo de campaña Google", options=GOOGLE_TYPES, key="g_tipo")
        gprod = pick("Producto / línea", PRODUCTOS, "g_prod")
        gobj = pick("Objetivo (opcional)", OBJETIVOS, "g_obj")
        gper = slug(st.text_input("Periodo (opcional)", key="g_periodo",
                                  placeholder="2026-q3, 2026-08, black-friday"))
        campaign = build_google_campaign(gtipo, gprod, gobj, gper)

        st.divider()
        st.subheader("Grupo de anuncios")
        if gtipo == "search":
            st.caption("Estructura: `tema_intencion_concordancia`")
            ag_tema = pick("Tema / servicio", PRODUCTOS, "ag_tema",
                           placeholder="resonancia, chequeo-ejecutivo…")
            ag_b = pick("Intención", INTENCIONES, "ag_int")
            ag_c = pick("Concordancia", CONCORDANCIAS, "ag_match")
        elif gtipo in ("pmax", "shopping"):
            st.caption("Grupo de recursos (asset group). Estructura: `producto_publico`")
            ag_tema = pick("Producto / línea", PRODUCTOS, "ag_prod")
            ag_b = pick("Público", PUBLICOS, "ag_pub")
            ag_c = ""
        else:  # display, video, gdemand
            st.caption("Estructura: `audiencia_formato`")
            ag_tema = pick("Audiencia", AUDIENCIAS, "ag_aud")
            ag_b = pick("Formato", FORMATOS, "ag_fmt")
            ag_c = ""
        ag_geo = pick("Geo (opcional)", GEOS, "ag_geo")
        ad_group = build_ad_group(ag_tema, ag_b, ag_c, ag_geo)
    else:
        manual = st.toggle("Escribir utm_campaign manual", key="camp_manual")
        if manual:
            campaign = slug(st.text_input("utm_campaign", key="camp_text",
                                          placeholder="meta_trafico_paquetes-preventivos"))
        else:
            st.markdown(f"Estructura: `{plataforma or 'plataforma'}_objetivo_producto`")
            objetivo = pick("Objetivo", OBJETIVOS, "objetivo")
            producto = pick("Producto / línea", PRODUCTOS, "producto")
            with st.expander("Opcional: geo y periodo"):
                geo = pick("Geo", GEOS, "geo")
                periodo = slug(st.text_input("Periodo", key="periodo", placeholder="2026-q3, 2026-08"))
            campaign = build_campaign(plataforma, objetivo, producto, geo, periodo)

    # ---- niveles de anuncio ----
    term = ""
    content = ""
    if not is_google:
        st.divider()
        if has_hierarchy:
            st.subheader("Niveles de anuncio")
            term = slug(st.text_input("utm_term — conjunto de anuncios (audiencia)", key="term",
                                      placeholder="lookalike-1-uio, intereses-salud…"))
            content = slug(st.text_input("utm_content — anuncio (creatividad)", key="content",
                                         placeholder="ig-video-15s-testimonial, fb-carrusel-a…"))
        else:
            content = slug(st.text_input("utm_content — pieza / creatividad (opcional)", key="content2",
                                         placeholder="cta-agenda, banner-a…"))


# ----------------------------------------------------------------------------
# Validación + salida
# ----------------------------------------------------------------------------
errors, warnings = url_issues(base_url)

if is_google:
    if not campaign:
        errors.append("Faltan datos para el nombre de campaña de Google (tipo y producto).")
else:
    if not source:
        errors.append("utm_source es obligatorio.")
    if not medium:
        errors.append("utm_medium es obligatorio.")
    if not campaign:
        errors.append("utm_campaign es obligatorio (completa objetivo y producto, o escríbelo manual).")

for w in warnings:
    st.warning(w)
for e in errors:
    st.error(e)


# ---- Google Ads: no UTMs, se entrega nombre de campaña + landing limpia ----
if is_google:
    st.subheader("Google Ads")
    st.write("No se agregan UTMs. Usa estos nombres dentro de Google Ads (GA4 los hereda vía el gclid):")

    st.markdown("**Campaña**")
    st.code(campaign or "google_tipo_[objetivo]_producto_[periodo]", language="text")

    if gtipo in ("pmax", "shopping"):
        st.markdown("**Grupo de recursos**")
        ag_hint = "producto_publico"
    elif gtipo == "search":
        st.markdown("**Grupo de anuncios**")
        ag_hint = "tema_intencion_concordancia"
    else:
        st.markdown("**Grupo de anuncios**")
        ag_hint = "audiencia_formato"
    st.code(ad_group or ag_hint, language="text")
    if not ad_group:
        st.caption("Completa los campos del grupo en la barra lateral.")

    st.markdown("**Landing** (URL limpia, sin UTM)")
    st.code(base_url or DEFAULT_BASE_URL, language="text")
    final_url = base_url

# ---- Resto de canales: URL con UTMs ----
else:
    params = build_params(source, medium, campaign, term, content)
    final_url = "" if errors else append_query_params(base_url, params)

    st.subheader("URL final")
    if final_url:
        st.code(final_url, language="text")
        if len(final_url) > 2000:
            st.warning("La URL supera 2.000 caracteres; acorta los valores.")
    else:
        st.info("Completa los campos obligatorios para generar la URL.")

    st.subheader("Vista previa de parámetros")
    if params:
        st.table([{"Parámetro": k, "Valor": v} for k, v in params])
    else:
        st.info("Completa los campos para ver los parámetros.")

# ---- Historial de la sesión ----
if final_url and not errors:
    if st.button("➕ Guardar en el historial", width="stretch"):
        fila = {
            "canal": channel_name,
            "utm_source": source,
            "utm_medium": medium,
            "utm_campaign": campaign,
            "utm_term": term,
            "utm_content": content,
            "ad_group": ad_group,
            "url": final_url,
        }
        if fila not in st.session_state.historial:
            st.session_state.historial.append(fila)

if st.session_state.historial:
    st.subheader("Historial de esta sesión")
    st.dataframe(st.session_state.historial, hide_index=True)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(st.session_state.historial[0].keys()))
    writer.writeheader()
    writer.writerows(st.session_state.historial)

    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Descargar CSV", buf.getvalue(), "utms-veris.csv",
                       "text/csv", width="stretch")
    if c2.button("🗑️ Vaciar historial", width="stretch"):
        st.session_state.historial = []
        st.rerun()

with st.expander("ℹ️ Reglas rápidas"):
    st.markdown(
        "**Formato** — todo en minúsculas, sin tildes ni espacios: `-` dentro de un bloque, "
        "`_` entre bloques (`meta_trafico_paquetes-preventivos`). La app lo normaliza sola.\n\n"
        "**Canales con UTM** (Meta, TikTok, mailing, WhatsApp, SMS, push)\n"
        "- `utm_source` = **plataforma**, no la red suelta: `meta`, `tiktok`, `mailing`, "
        "`whatsapp`, `sms`, `push`. Nada de `instagram` / `facebook`.\n"
        "- `utm_medium` = **cómo llega el tráfico**: `paid` para pauta · `email`, `chat`, "
        "`sms`, `push` para los directos.\n"
        "- `utm_campaign` = `plataforma_objetivo_producto`, con `_geo` y `_periodo` opcionales "
        "al final (`meta_conversion_citas_uio_2026-q3`).\n"
        "- `utm_term` = conjunto de anuncios / audiencia · `utm_content` = anuncio. "
        "Solo Meta y TikTok tienen los dos niveles; el resto usa únicamente `utm_content`.\n"
        "- En Meta, Instagram vs Facebook se marca en `utm_content` (`ig-video-15s`, "
        "`fb-carrusel-a`).\n\n"
        "**Google Ads** — no lleva UTM manual: el auto-tagging (`gclid`) pasa los nombres a GA4. "
        "Se nombra dentro de la cuenta:\n"
        "- Campaña = `google_tipo_[objetivo]_producto_[periodo]` "
        "(`google_search_conversion_cardiologia_2026-q3`).\n"
        "- Grupo de anuncios según el tipo: `tema_intencion_concordancia` en search · "
        "`producto_publico` en pmax/shopping (grupo de recursos) · `audiencia_formato` en "
        "display/video/gdemand. Se le puede añadir `_geo` al final.\n"
        "- Un grupo = una intención, y sin fechas: el periodo vive en la campaña.\n\n"
        "**Siempre** — aterriza en `www.veris.com.ec`, no etiquetes enlaces internos del sitio "
        "y nunca metas datos personales (cédula, correo, teléfono) en un parámetro."
    )
