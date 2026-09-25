"""
Alertas viales via Google News RSS + Nitter (fallback).

Fuente primaria: Google News RSS — busca noticias de medios mexicanos
(El Universal, Milenio, Reforma, etc.) sobre incidentes en las carreteras
del path activo. Sin API key, sin costo, muy estable.

Fallback: Nitter RSS de @SCT_mx / @CAPUFE_Oficial si Google News no responde.
"""
import asyncio
import hashlib
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

# ── Google News RSS ────────────────────────────────────────────────────────────
GNEWS_URL = "https://news.google.com/rss/search"
GNEWS_PARAMS = {"hl": "es-419", "gl": "MX", "ceid": "MX:es-419"}

# Palabras clave base para cualquier consulta vial
_KW_BASE = "carretera (accidente OR cierre OR bloqueo OR derrumbe OR volcadura OR inundacion)"

# ── Nitter (fallback) ──────────────────────────────────────────────────────────
NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.1d4.us",
    "https://nitter.kavin.rocks",
]
VIAL_ACCOUNTS = ["SCT_mx", "CAPUFE_Oficial", "CondeBloqueos", "InfoBloqueos"]

# ── Clasificación ──────────────────────────────────────────────────────────────
_KEYWORDS_RELEVANTES = [
    "cierre", "cerrado", "accidente", "choque", "volcadura",
    "bloqueo", "derrumbe", "inundacion", "neblina", "niebla",
    "carretera", "autopista", "mex-", "libramiento",
    "reten", "retén", "operativo", "manifestacion", "protesta",
]

_INCIDENT_PATTERNS: list[tuple[tuple[str, str], list[str]]] = [
    (("🚧", "Cierre vial"),       ["cierre", "cerrado", "bloqueado", "bloqueo", "corte"]),
    (("🚨", "Accidente"),         ["accidente", "choque", "volcadura", "colision"]),
    (("⚠️", "Peligro en ruta"),  ["derrumbe", "deslizamiento", "neblina", "niebla", "inundacion"]),
    (("📢", "Manifestación"),     ["manifestacion", "protesta", "marcha", "paro"]),
    (("👮", "Operativo/Retén"),   ["reten", "retén", "operativo", "revision"]),
]


def _clasificar(texto: str) -> tuple[str, str]:
    t = texto.lower()
    for (emoji, tipo), kws in _INCIDENT_PATTERNS:
        if any(k in t for k in kws):
            return emoji, tipo
    return "📡", "Aviso vial"


def _es_relevante(texto: str, highways: set[str], city_labels: list[str]) -> bool:
    t = texto.lower()
    if not any(k in t for k in _KEYWORDS_RELEVANTES):
        return False
    if highways or city_labels:
        hws_lower = {h.lower() for h in highways}
        cities_lower = [c.lower() for c in city_labels]
        return (
            any(h in t for h in hws_lower)
            or any(c in t for c in cities_lower)
        )
    return True


def _to_alerta(texto: str, fuente: str = "Noticias") -> dict:
    emoji, tipo = _clasificar(texto)
    h = hashlib.md5(texto[:80].encode()).hexdigest()[:12]
    return {
        "tipo": tipo,
        "emoji": emoji,
        "descripcion": texto,
        "autor": None,
        "hora": None,
        "severidad": 0,
        "fuente": fuente,
        "coords": None,
        "cierre_hash": None,
        "tweet_hash": h,
    }


# ── Google News RSS ────────────────────────────────────────────────────────────

def _build_query(highways: set[str], city_labels: list[str]) -> str:
    """Construye la query de búsqueda combinando keywords de la ruta."""
    parts = [_KW_BASE]
    if highways:
        hw_q = " OR ".join(f'"{h}"' for h in sorted(highways)[:4])
        parts.append(f"({hw_q})")
    elif city_labels:
        city_q = " OR ".join(f'"{c}"' for c in city_labels[:4])
        parts.append(f"({city_q})")
    return " ".join(parts)


def _parse_gnews(xml_text: str) -> list[str]:
    """Extrae títulos de artículos de las últimas 6 horas del RSS de Google News."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    titles = []
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
            pass
        title = item.findtext("title") or ""
        if title:
            titles.append(title.strip())
    return titles


async def _fetch_gnews(
    client: httpx.AsyncClient, highways: set[str], city_labels: list[str]
) -> tuple[list[str], bool]:
    """Retorna (títulos, disponible)."""
    query = _build_query(highways, city_labels)
    try:
        r = await client.get(
            GNEWS_URL,
            params={**GNEWS_PARAMS, "q": query},
            timeout=10,
            follow_redirects=True,
        )
        r.raise_for_status()
        return _parse_gnews(r.text), True
    except Exception:
        return [], False


# ── Nitter fallback ────────────────────────────────────────────────────────────

def _parse_nitter_rss(xml_text: str, account: str) -> list[str] | None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    titles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    for item in root.findall(".//item"):
        pub = item.findtext("pubDate") or ""
        try:
            dt = parsedate_to_datetime(pub)
            if dt < cutoff:
                continue
        except Exception:
            pass
        title = item.findtext("title") or ""
        if title and not title.startswith("RT by"):
            titles.append(title[:300])
    return titles


async def _fetch_nitter_account(
    client: httpx.AsyncClient, instance: str, account: str
) -> list[str] | None:
    try:
        r = await client.get(
            f"{instance}/{account}/rss", timeout=7, follow_redirects=True
        )
        if r.status_code != 200:
            return None
        return _parse_nitter_rss(r.text, account)
    except Exception:
        return None


async def _fetch_nitter() -> tuple[list[str], bool]:
    """Prueba instancias Nitter en paralelo. Retorna (títulos, disponible)."""
    for instance in NITTER_INSTANCES:
        async with httpx.AsyncClient() as client:
            results = await asyncio.gather(
                *[_fetch_nitter_account(client, instance, acc) for acc in VIAL_ACCOUNTS]
            )
        if all(r is None for r in results):
            continue  # instancia caída, probar la siguiente
        titles = []
        for r in results:
            if r:
                titles.extend(r)
        return titles, True
    return [], False


# ── Función principal ──────────────────────────────────────────────────────────

async def _get_alertas(
    highways: set[str], city_labels: list[str]
) -> tuple[list[dict], bool]:
    """
    1. Intenta Google News RSS (principal).
    2. Si falla, intenta Nitter RSS (fallback).
    Retorna (alertas_filtradas, disponible).
    """
    async with httpx.AsyncClient() as client:
        titles, gnews_up = await _fetch_gnews(client, highways, city_labels)

    fuente = "Google News"
    disponible = gnews_up

    if not gnews_up:
        titles, nitter_up = await _fetch_nitter()
        fuente = "X/Twitter"
        disponible = nitter_up

    seen: set[str] = set()
    alerts: list[dict] = []
    for title in titles:
        if not _es_relevante(title, highways, city_labels):
            continue
        key = title[:50]
        if key in seen:
            continue
        seen.add(key)
        alerts.append(_to_alerta(title, fuente))

    return alerts[:5], disponible


# ── API pública (mismas firmas que antes) ──────────────────────────────────────

async def get_tweets_for_city_route(
    city_path: list[str],
) -> tuple[list[dict], bool]:
    from regions.city_graph import CITY_EDGES, CITY_LABELS

    highways: set[str] = set()
    city_labels: list[str] = []
    for i in range(len(city_path) - 1):
        hw = CITY_EDGES.get(city_path[i], {}).get(city_path[i + 1])
        if hw:
            highways.add(hw)
    for c in city_path:
        label = CITY_LABELS.get(c)
        if label:
            city_labels.append(label)

    return await _get_alertas(highways, city_labels)


async def get_tweets_for_regions(
    region_keys: list[str],
) -> tuple[list[dict], bool]:
    return await _get_alertas(set(), [])
