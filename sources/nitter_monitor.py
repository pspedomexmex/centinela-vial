"""
Alertas viales via RSS de cuentas X/Twitter (@SCT_mx, @CAPUFE_Oficial, etc.)
Usa instancias públicas de Nitter — sin API key ni costo.
Fallback automático entre instancias si alguna falla o está caída.
"""
import asyncio
import hashlib
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

# Instancias Nitter en orden de preferencia
NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.1d4.us",
    "https://nitter.kavin.rocks",
]

# Cuentas viales mexicanas a monitorear
VIAL_ACCOUNTS = [
    "SCT_mx",
    "CAPUFE_Oficial",
    "CondeBloqueos",
    "InfoBloqueos",
]

# Palabras clave mínimas para considerar un tweet relevante para carga
_KEYWORDS = [
    "cierre", "cerrado", "accidente", "choque", "volcadura",
    "bloqueo", "derrumbe", "inundacion", "neblina", "niebla",
    "carretera", "autopista", "mex-", "libramiento",
    "reten", "retén", "operativo", "manifestacion", "protesta", "paro",
]

_INCIDENT_PATTERNS: list[tuple[tuple[str, str], list[str]]] = [
    (("🚧", "Cierre vial"),        ["cierre", "cerrado", "bloqueado", "bloqueo", "corte"]),
    (("🚨", "Accidente"),          ["accidente", "choque", "volcadura", "colision"]),
    (("⚠️", "Peligro en ruta"),   ["derrumbe", "deslizamiento", "neblina", "niebla", "inundacion"]),
    (("📢", "Manifestación"),      ["manifestacion", "protesta", "marcha", "paro"]),
    (("👮", "Operativo/Retén"),    ["reten", "retén", "operativo", "revision"]),
]


def _clasificar(texto: str) -> tuple[str, str]:
    t = texto.lower()
    for (emoji, tipo), kws in _INCIDENT_PATTERNS:
        if any(k in t for k in kws):
            return emoji, tipo
    return "📡", "Aviso vial"


def _es_relevante(texto: str, highways: set[str], city_labels: list[str]) -> bool:
    t = texto.lower()
    # 1. Debe contener al menos una palabra clave vial
    if not any(k in t for k in _KEYWORDS):
        return False
    # 2. Si hay ruta activa, debe mencionar alguna highway o ciudad del path
    if highways or city_labels:
        hws_lower = {h.lower() for h in highways}
        cities_lower = [c.lower() for c in city_labels]
        return (
            any(h in t for h in hws_lower)
            or any(c in t for c in cities_lower)
        )
    return True


def _parse_rss(xml_text: str, account: str) -> list[dict] | None:
    """Parsea RSS de Nitter. Retorna None si el XML está malformado."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    tweets = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    for item in root.findall(".//item"):
        pub_str = item.findtext("pubDate") or ""
        try:
            dt = parsedate_to_datetime(pub_str) if pub_str else None
            if dt and dt < cutoff:
                continue  # Tweet demasiado antiguo
        except Exception:
            pass

        title = item.findtext("title") or ""
        # Nitter prefija retweets con "RT by @cuenta: " — los ignoramos
        if title.startswith("RT by"):
            continue

        tweets.append({"texto": title[:300], "account": account, "pub": pub_str})
    return tweets


async def _fetch_account(
    client: httpx.AsyncClient, instance: str, account: str
) -> list[dict] | None:
    """Retorna lista de tweets o None si la instancia falló."""
    try:
        r = await client.get(
            f"{instance}/{account}/rss",
            timeout=8,
            follow_redirects=True,
        )
        if r.status_code != 200:
            return None
        return _parse_rss(r.text, account)
    except Exception:
        return None


async def _fetch_from_instance(instance: str) -> list[dict] | None:
    """
    Intenta obtener tweets de todas las cuentas en una instancia.
    Retorna None si la instancia está caída, lista (vacía o no) si responde.
    """
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_fetch_account(client, instance, acc) for acc in VIAL_ACCOUNTS]
        )
    if all(r is None for r in results):
        return None  # instancia caída
    tweets = []
    for r in results:
        if r:
            tweets.extend(r)
    return tweets


async def _get_raw_tweets() -> tuple[list[dict], bool]:
    """
    Prueba instancias Nitter en paralelo y usa la primera que responda.
    Retorna (tweets, disponible) — disponible=False si todas las instancias fallaron.
    """
    tasks = [_fetch_from_instance(inst) for inst in NITTER_INSTANCES]
    any_up = False
    for coro in asyncio.as_completed(tasks):
        result = await coro
        if result is not None:
            any_up = True
            if result:
                return result, True
    return [], any_up


def _to_alerta(tweet: dict) -> dict:
    texto = tweet["texto"]
    emoji, tipo = _clasificar(texto)
    # Hash estable para dedup del monitor (sin hora)
    h = hashlib.md5(texto[:80].encode()).hexdigest()[:12]
    return {
        "tipo": tipo,
        "emoji": emoji,
        "descripcion": texto,
        "autor": f"@{tweet['account']}",
        "hora": None,
        "severidad": 0,
        "fuente": "X/Twitter",
        "coords": None,
        "cierre_hash": None,
        "tweet_hash": h,
    }


async def get_tweets_for_city_route(
    city_path: list[str],
) -> tuple[list[dict], bool]:
    """
    Retorna (alerts, disponible).
    disponible=False si todas las instancias Nitter fallaron.
    Filtra por highways y ciudades del path.
    """
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

    raw, disponible = await _get_raw_tweets()
    seen: set[str] = set()
    alerts: list[dict] = []
    for tw in raw:
        if not _es_relevante(tw["texto"], highways, city_labels):
            continue
        key = tw["texto"][:50]
        if key in seen:
            continue
        seen.add(key)
        alerts.append(_to_alerta(tw))

    return alerts[:5], disponible


async def get_tweets_for_regions(
    region_keys: list[str],
) -> tuple[list[dict], bool]:
    """
    Retorna (alerts, disponible) sin filtro de ruta (fallback regional).
    """
    raw, disponible = await _get_raw_tweets()
    seen: set[str] = set()
    alerts: list[dict] = []
    for tw in raw:
        if not _es_relevante(tw["texto"], set(), []):
            continue
        key = tw["texto"][:50]
        if key in seen:
            continue
        seen.add(key)
        alerts.append(_to_alerta(tw))
    return alerts[:5], disponible
