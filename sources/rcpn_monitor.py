"""
Monitor de noticias sobre la Resistencia Civil Pacífica Nacional (RCPN)
y Arturo Morales Zaragoza.

Fuentes:
  - Google News RSS (5 queries, agrega El Universal, Proceso, La Jornada, etc.)
  - Nitter RSS de cuentas X/Twitter de RCPN y movimientos afines
Ventana: 30 días. Sin API key.
"""
import asyncio
import hashlib
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

# ── Configuración general ──────────────────────────────────────────────────────
GNEWS_URL    = "https://news.google.com/rss/search"
GNEWS_PARAMS = {"hl": "es-419", "gl": "MX", "ceid": "MX:es-419"}

DIAS_RECIENTE = 2    # umbral "últimas 48h"
DIAS_SEMANA   = 8    # umbral "esta semana"
MAX_DIAS      = 30   # ventana total

# ── Queries Google News ────────────────────────────────────────────────────────
# Estrategia: primero queries exactas (alta precisión), luego amplias (más cobertura).
# Query 2 ("Resistencia Civil Pacífica Nacional") devuelve la noticia de Palalia's Tours.
# 3 queries: suficiente cobertura sin saturar Google News desde Vercel
_GNEWS_QUERIES: list[tuple[str, str]] = [
    # Nombre exacto de la organización — la más precisa (~10 resultados)
    ('"Resistencia Civil Pacífica Nacional"',                                              "Google News"),
    # Acciones civiles: marchas, bloqueos, cierres (~10 resultados)
    ('"resistencia civil pacífica" México bloqueo OR marcha OR plantón OR cierre',         "Google News"),
    # Represión y violencia contra colectivos civiles — Lechería-Texcoco, Oaxaca, etc.
    ('"resistencia civil" México muertos OR heridos OR represión OR agresión OR detenidos', "Google News"),
]


# Cuentas de RCPN y movimientos civiles afines en México
# (placeholder — activar cuando RCPN abra canal de Twitter/Telegram)
RCPN_ACCOUNTS: list[tuple[str, str]] = []

# ── Filtro de exclusión ───────────────────────────────────────────────────────
# Noticias que NO son de resistencia civil aunque aparezcan en las queries.

# Temas de Morena/AMLO como sujeto principal (no como blanco de protesta)
_KW_MORENA = [
    "regeneración nacional", "movimiento de regeneración",
    "andrés manuel", "lópez obrador", "amlo",
    "cuarta transformación", "4t ", "4t.",
    "morena gana", "morena triunfa", "morena celebra", "morena conmemora",
    "claudia sheinbaum",
]

# Desastres naturales sin contexto de resistencia civil
_KW_DESASTRE = [
    "huracán", "hurricane", "tormenta tropical", "ciclón",
    "terremoto", "sismo de", "alerta máxima por",
]

# Presencia de estas palabras salva la nota aunque tenga keywords de arriba
_KW_RESISTENCIA = [
    "resistencia", "marcha", "protesta", "plantón", "manifestación",
    "rcpn", "bloqueo", "cierre", "convocatoria", "oposición ciudadana",
    "arturo morales",
]


def _excluir(titulo: str) -> bool:
    """True = descartar la noticia."""
    t = titulo.lower()
    tiene_resistencia = any(k in t for k in _KW_RESISTENCIA)

    # Siempre descartar desastres naturales (huracán, sismo, etc.)
    if any(k in t for k in _KW_DESASTRE):
        return True

    # Descartar si el tema es Morena/AMLO y NO hay contexto de protesta/resistencia
    if any(k in t for k in _KW_MORENA) and not tiene_resistencia:
        return True

    return False


# ── Clasificación por tipo de evento ──────────────────────────────────────────
_CLASIFICACION: list[tuple[tuple[str, str], list[str]]] = [
    (("🚨", "Represión"),      ["detenido", "detención", "represión", "agresión",
                                 "violencia", "arrestado", "preso", "golpeado", "desaparecido"]),
    (("✅", "Logro"),          ["victoria", "logro", "ganó", "revocó", "aprobó",
                                 "triunfo", "reconoce", "acuerdo favorable"]),
    (("🚶", "Movilización"),   ["marcha", "manifestación", "plantón", "concentración",
                                 "mitin", "convocatoria", "movilización", "protesta"]),
    (("⚖️", "Legal/Político"), ["demanda", "amparo", "juicio", "resolución", "electoral",
                                 "voto", "ine", "tribunal", "fraude", "candidatura", "tepjf"]),
    (("📢", "Declaración"),    ["declaró", "anunció", "exige", "denuncia", "señaló",
                                 "llamó", "comunicado", "advierte", "exhortó"]),
]

_MESES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]


def _clasificar(texto: str) -> tuple[str, str]:
    t = texto.lower()
    for (emoji, tipo), kws in _CLASIFICACION:
        if any(k in t for k in kws):
            return emoji, tipo
    return "📰", "Noticia"


def _fmt_fecha(dt: datetime) -> str:
    """'13 oct' en zona México UTC-6."""
    from datetime import timedelta
    mx = dt.astimezone(timezone(timedelta(hours=-6)))
    return f"{mx.day} {_MESES[mx.month - 1]}"


# ── Parsers de RSS ─────────────────────────────────────────────────────────────

def _parse_gnews(xml_text: str, fuente_default: str = "Google News",
                 max_days: int = MAX_DIAS) -> list[dict]:
    """
    Parsea RSS de Google News.
    Extrae: título, link, nombre de la fuente original, fecha.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    for item in root.findall(".//item"):
        pub = item.findtext("pubDate") or ""
        try:
            dt = parsedate_to_datetime(pub)
            if dt < cutoff:
                continue
        except Exception:
            dt = datetime.now(timezone.utc)

        title = (item.findtext("title") or "").strip()
        if not title:
            continue

        # Link al artículo original
        link = (item.findtext("link") or "").strip()

        # Google News incluye <source url="...">Nombre Medio</source>
        src_el = item.find("source")
        if src_el is not None:
            fuente_nombre = (src_el.text or fuente_default).strip()
        else:
            fuente_nombre = fuente_default

        items.append({
            "title":  title,
            "link":   link,
            "fuente": fuente_nombre,
            "dt":     dt,
        })
    return items


def _parse_nitter(xml_text: str, cuenta: str, fuente_label: str,
                  max_days: int = MAX_DIAS) -> list[dict]:
    """Parsea RSS de Nitter (tweet = título del item)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    for item in root.findall(".//item"):
        if (item.findtext("title") or "").startswith("RT by"):
            continue
        pub = item.findtext("pubDate") or ""
        try:
            dt = parsedate_to_datetime(pub)
            if dt < cutoff:
                continue
        except Exception:
            dt = datetime.now(timezone.utc)
        title = (item.findtext("title") or "").strip()
        link  = (item.findtext("link")  or "").strip()
        if title:
            items.append({"title": title, "link": link, "fuente": fuente_label, "dt": dt})
    return items


# ── Fetchers async ─────────────────────────────────────────────────────────────

_TIMEOUT = httpx.Timeout(connect=4.0, read=6.0, write=3.0, pool=3.0)


async def _fetch_gnews(client: httpx.AsyncClient,
                       query: str, fuente_label: str) -> list[dict]:
    try:
        r = await client.get(
            GNEWS_URL,
            params={**GNEWS_PARAMS, "q": query},
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        r.raise_for_status()
        return _parse_gnews(r.text, fuente_default=fuente_label)
    except Exception:
        return []


# ── Función principal ──────────────────────────────────────────────────────────

async def get_rcpn_noticias() -> list[dict]:
    """
    Consulta Google News con 6 queries en paralelo.
    Retorna lista deduplicada ≤30 items, más reciente primero.
    Cada item: {titulo, link, fuente, emoji, tipo, fecha, hash}
    """
    async with httpx.AsyncClient() as client:
        gnews_lotes = await asyncio.gather(*[
            _fetch_gnews(client, q, label) for q, label in _GNEWS_QUERIES
        ])

    seen: set[str] = set()
    noticias: list[dict] = []

    for lote in gnews_lotes:
        for item in lote:
            if _excluir(item["title"]):
                continue
            key = item["title"][:50]
            if key in seen:
                continue
            seen.add(key)
            emoji, tipo = _clasificar(item["title"])
            h = hashlib.md5(item["title"][:80].encode()).hexdigest()[:12]
            noticias.append({
                "titulo": item["title"],
                "link":   item.get("link", ""),
                "fuente": item.get("fuente", "Google News"),
                "emoji":  emoji,
                "tipo":   tipo,
                "fecha":  _fmt_fecha(item["dt"]),
                "dt":     item["dt"],
                "hash":   h,
            })

    noticias.sort(key=lambda x: x["dt"], reverse=True)
    return noticias[:30]
