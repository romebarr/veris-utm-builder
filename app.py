"""
UTM Builder — Veris (v1.3)
Nomenclatura estándar para campañas: Meta, TikTok, Google, mail, WhatsApp, SMS, push.

- utm_source   = plataforma (meta, tiktok, mailing, whatsapp, sms, push)
- utm_medium   = paid para pauta; email / chat / sms / push para los directos
- utm_campaign = plataforma_objetivo_producto  (+ _geo _periodo opcionales)
- utm_term     = conjunto de anuncios: audiencia (+ _geo)  -> solo canales con jerarquía (Meta/TikTok)
- utm_content  = anuncio: formato-tema-version (en Meta, ig- / fb- delante si es de una sola red)
- Regla de oro = cada nombre se crea aquí y se copia igual a la plataforma y al UTM.
                 Los UTM se llenan a mano: no se usan parámetros dinámicos ({{campaign.name}}).
- Google Ads   = auto-tagging (gclid) activo + sufijo de URL final con
                 utm_source=google&utm_medium=cpc&utm_campaign=<nombre de la campaña>.
                 campaña      google_tipo_[objetivo]_producto_[periodo]
                 grupo        tema_intencion_concordancia   (search)
                              producto_publico               (pmax/shopping)
                              audiencia_formato              (display/video/gdemand)

Ejecutar local:  streamlit run app.py
"""

import io
import csv
import hmac
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
    "Google Ads":                  {"google": True,        "source": "google",   "medium": "cpc",         "plataforma": "google"},
    "Email / Mailing":             {"source": "mailing",   "medium": "email",       "plataforma": "mail",     "hierarchy": False},
    "WhatsApp":                    {"source": "whatsapp",  "medium": "chat",        "plataforma": "whatsapp", "hierarchy": False},
    "SMS":                         {"source": "sms",       "medium": "sms",         "plataforma": "sms",      "hierarchy": False},
    "Push (web/app)":              {"source": "push",      "medium": "push",        "plataforma": "push",     "hierarchy": False},
    "Otro (personalizado)":        {"otro": True,          "plataforma": ""},
}

# Tipos de campaña de Google Ads.
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

# Audiencias del conjunto de anuncios en Meta / TikTok (utm_term).
AUDIENCIAS_SOCIAL = ["intereses-salud", "similares", "remarketing-30d", "remarketing-90d",
                     "datos-propios", "amplia"]

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


def slug_blocks(value: str) -> str:
    """Como slug(), pero respeta '_' como separador de bloques.

    'Meta_Conversion_Citas UIO' -> 'meta_conversion_citas-uio'
    """
    if not value:
        return ""
    return "_".join(b for b in (slug(x) for x in value.split("_")) if b)


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
    """Añade UTMs respetando query existente y fragmento (#).

    Quita todos los utm_* que ya traiga la URL, aunque no se vayan a reemplazar:
    un utm_term viejo no debe sobrevivir junto a una campaña nueva.
    """
    if not params:
        return url
    parts = urlsplit(url)
    existing = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                if not k.lower().startswith("utm_")]
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
        warnings.append("La URL base ya trae parámetros `utm_*`: se reemplazan todos por los de abajo.")
    return errors, warnings


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
st.set_page_config(page_title="UTM Builder — Veris", page_icon="🔗", layout="centered")

# ----------------------------------------------------------------------------
# Acceso
# ----------------------------------------------------------------------------
# Dos contraseñas (Veris y agencia) definidas en .streamlit/secrets.toml.
# Solo cierran la app al publico: adentro los dos perfiles ven exactamente lo mismo.
PERFILES = {"veris": "Veris", "agencia": "Agencia"}


def claves_configuradas() -> Dict[str, str]:
    try:
        return {k: str(v) for k, v in st.secrets["passwords"].items()}
    except Exception:
        return {}


def puerta() -> bool:
    if st.session_state.get("perfil"):
        return True

    st.title("🔗 UTM Builder — Veris")
    st.caption("Herramienta interna. Ingresa la contraseña que te compartieron.")

    claves = claves_configuradas()
    if not claves:
        st.error(
            "No hay contraseñas configuradas. Crea `.streamlit/secrets.toml` con una "
            "sección `[passwords]` (ver `secrets.toml.example`)."
        )
        return False

    with st.form("login"):
        clave = st.text_input("Contraseña", type="password")
        entrar = st.form_submit_button("Entrar")

    if entrar:
        for perfil, esperada in claves.items():
            if hmac.compare_digest(clave, esperada):
                st.session_state.perfil = perfil
                st.rerun()
        st.error("Contraseña incorrecta.")

    return False


if not puerta():
    st.stop()

st.title("🔗 UTM Builder — Veris")
st.caption("Construye URLs de campaña con nomenclatura estándar. Todo se normaliza a minúsculas, sin tildes ni espacios.")

if "historial" not in st.session_state:
    st.session_state.historial = []

with st.sidebar:
    perfil_actual = st.session_state.get("perfil", "")
    st.caption(f"Sesión: **{PERFILES.get(perfil_actual, perfil_actual)}**")
    if st.button("Salir", width="stretch"):
        st.session_state.pop("perfil", None)
        st.rerun()
    st.divider()

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
        plataforma, source, medium = "google", channel["source"], channel["medium"]
        st.info("Google Ads: deja el auto-tagging (gclid) activo **y además** pega el sufijo "
                "de URL final que entrega la app, con el nombre exacto de la campaña.")
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
            campaign = slug_blocks(st.text_input("utm_campaign", key="camp_text",
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
            st.caption("Conjunto de anuncios: `audiencia` + `_geo` opcional")
            t_aud = pick("Audiencia del conjunto", AUDIENCIAS_SOCIAL, "t_aud",
                         placeholder="intereses-maternidad, similares-compradores…")
            t_geo = pick("Geo del conjunto (opcional)", GEOS, "t_geo")
            term = build_ad_group(t_aud, t_geo)
            content = slug(st.text_input("utm_content — anuncio: formato-tema-version", key="content",
                                         placeholder="video-15s-testimonial-v2, ig-carrusel-a…"))
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
elif has_hierarchy:
    for valor, nivel in ((source, "utm_source"), (medium, "utm_medium"), (campaign, "utm_campaign"),
                         (term, "el conjunto (audiencia)"), (content, "el anuncio (utm_content)")):
        if not valor:
            errors.append(f"Falta {nivel}: el nombre en la plataforma y el UTM tienen que existir los dos.")
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


# ---- Google Ads: nombres + sufijo de URL final ----
if is_google:
    st.subheader("Google Ads")
    st.write("1. Copia estos nombres tal cual dentro de Google Ads.")

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

    params = build_params(source, medium, campaign, "", "")
    sufijo = urlencode(params, quote_via=quote, safe="-._~") if campaign else ""
    st.write("2. En la campaña: **Configuración → Opciones de URL de la campaña → Sufijo de URL final**. "
             "Deja el auto-tagging (gclid) activo.")
    st.code(sufijo or "utm_source=google&utm_medium=cpc&utm_campaign=<nombre de la campaña>", language="text")
    st.caption("El utm_campaign del sufijo y el nombre de la campaña tienen que ser idénticos. "
               "Los reportes de BigQuery leen los UTM: sin sufijo, las visitas cuentan como búsqueda orgánica.")

    st.markdown("**URL final de los anuncios** (landing sin UTM; el sufijo se agrega solo)")
    st.code(base_url or DEFAULT_BASE_URL, language="text")
    final_url = "" if errors else append_query_params(base_url, params)

# ---- Resto de canales: URL con UTMs ----
else:
    params = build_params(source, medium, campaign, term, content)
    final_url = "" if errors else append_query_params(base_url, params)

    if has_hierarchy:
        st.subheader("1 · Nombres para la plataforma")
        st.write("Copia cada nombre y pégalo **tal cual** en la plataforma. No los escribas de nuevo: "
                 "así el nombre y el UTM coinciden y la pauta se puede cruzar con Analytics.")
        st.markdown("**Campaña**")
        st.code(campaign or "plataforma_objetivo_producto", language="text")
        st.markdown("**Conjunto de anuncios**")
        st.code(term or "audiencia_geo", language="text")
        st.markdown("**Anuncio**")
        st.code(content or "formato-tema-version", language="text")
        st.caption("Si después se renombra la campaña, el conjunto o el anuncio en la plataforma, "
                   "hay que volver a generar la URL aquí y reemplazarla en todos sus anuncios.")
        st.subheader("2 · URL final (campo «URL del sitio web» del anuncio)")
    else:
        st.write("Copia el nombre de campaña al nombre del envío en la herramienta, para que coincidan.")
        st.markdown("**Nombre del envío**")
        st.code(campaign or "plataforma_objetivo_producto", language="text")
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
            "sufijo_google": sufijo if is_google else "",
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
        "- En Meta, si el anuncio es de una sola red, se marca delante en `utm_content` "
        "(`ig-video-15s`, `fb-carrusel-a`).\n\n"
        "**Regla de oro** — cada nombre se crea aquí y se pega igual en la plataforma y en el UTM. "
        "Los UTM se llenan a mano con esta app: no usamos los parámetros automáticos de Meta o TikTok "
        "(`{{campaign.name}}`), porque si se edita un nombre no se actualizan.\n\n"
        "**Google Ads** — auto-tagging (`gclid`) activo **y además** el sufijo de URL final "
        "`utm_source=google&utm_medium=cpc&utm_campaign=<nombre>`. Se nombra dentro de la cuenta:\n"
        "- Campaña = `google_tipo_[objetivo]_producto_[periodo]` "
        "(`google_search_conversion_cardiologia_2026-q3`).\n"
        "- Grupo de anuncios según el tipo: `tema_intencion_concordancia` en search · "
        "`producto_publico` en pmax/shopping (grupo de recursos) · `audiencia_formato` en "
        "display/video/gdemand. Se le puede añadir `_geo` al final.\n"
        "- Un grupo = una intención, y sin fechas: el periodo vive en la campaña."
    )
