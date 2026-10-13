"""
Monitor de noticias sobre la Resistencia Civil Pacífica Nacional (RCPN)
y Arturo Morales Zaragoza vía Google News RSS.
Sin API key — ventana de 15 días.
"""
import asyncio
import hashlib
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

GNEWS_URL    = "https://news.google.com/rss/search"
GNEWS_PARAMS = {"hl": "es-419", "gl": "MX", "ceid": "MX:es-419"}

DIAS_RECIENTE = 2    # umbral "últimas 48h"
DIAS_SEMANA   = 7    # umbral "esta semana"
MAX_DIAS      = 15   # ventana total de búsqueda

# Tres queries en paralelo para máxima cobertura
_QUERIES = [
    '"Resistencia Civil Pacífica Nacional"',
    '"Arturo Morales" (resistencia OR RCPN OR "justicia ciudadana")',
    'RCPN México (marcha OR manifestación OR plantón OR convocatoria)',
]

# Clasificación por tipo de evento
_CLASIFICACION: list[tuple[tuple[str, str], list[str]]] = [
    (("🚨", "Represión"),      ["detenido", "detención", "represión", "agresión", "violencia", "arrestado", "preso", "golpeado"]),
    (("✅", "Logro"),          ["victoria", "logro", "ganó", "revocó", "aprobó", "triunfo", "reconoce"]),
    (("🚶", "Movilización"),   ["marcha", "manifestación", "plantón", "concentración", "mitin", "convocatoria", "movilización"]),
    (("⚖️", "Legal/Político"), ["demanda", "amparo", "juicio", "resolución", "electoral", "voto", "ine", "tribunal", "fraude", "candidatura"]),
    (("📢", "Declaración"),    ["declaró", "anunció", "exige", "denuncia", "señaló", "llamó", "comunicado", "advierte"]),
]


def _clasificar(texto: str) -> tuple[str, str]:
    t = texto.lower()
    for (emoji, tipo), kws in _CLASIFICACION:
        if any(k in t for k in kws):
            return emoji, tipo
    return "📰", "Noticia"


def _parse_items(xml_text: str, max_days: int = MAX_DIAS) -> list[dict]:
    """Parsea RSS de Google News. Retorna items dentro de la ventana de tiempo."""
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
        if title:
            items.append({"title": title, "dt": dt})
    return items


async def _fetch(client: httpx.AsyncClient, query: str) -> list[dict]:
    try:
        r = await client.get(
            GNEWS_URL,
            params={**GNEWS_PARAMS, "q": query},
            timeout=10,
            follow_redirects=True,
        )
        r.raise_for_status()
        return _parse_items(r.text)
    except Exception:
        return []


async def get_rcpn_noticias() -> list[dict]:
    """
    Lanza 3 queries en paralelo a Google News RSS.
    Retorna lista deduplicada de hasta 20 noticias, más reciente primero.
    Cada item: {titulo, emoji, tipo, dt, hash}
    """
    async with httpx.AsyncClient() as client:
        lotes = await asyncio.gather(*[_fetch(client, q) for q in _QUERIES])

    seen: set[str] = set()
    noticias: list[dict] = []
    for lote in lotes:
        for item in lote:
            key = item["title"][:50]
            if key in seen:
                continue
            seen.add(key)
            emoji, tipo = _clasificar(item["title"])
            h = hashlib.md5(item["title"][:80].encode()).hexdigest()[:12]
            noticias.append({
                "titulo": item["title"],
                "emoji":  emoji,
                "tipo":   tipo,
                "dt":     item["dt"],
                "hash":   h,
            })

    noticias.sort(key=lambda x: x["dt"], reverse=True)
    return noticias[:20]
