"""
Noticias de robos a transporte de carga en carretera vía Google News RSS.
Sin API key. Geocodifica la ubicación aproximada desde el texto de la noticia.
"""
import asyncio
import hashlib
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

GNEWS_URL    = "https://news.google.com/rss/search"
GNEWS_PARAMS = {"hl": "es-419", "gl": "MX", "ceid": "MX:es-419"}

_KW_ROBOS   = ('(robo OR asalto) (transportista OR "transporte de carga" OR '
               'camion OR trailer OR tractocamion) (carretera OR autopista)')
_KW_OFICIAL = ('"robo a transportista" OR "pirateria terrestre" OR '
               '"robo de carga" (carretera OR autopista)')


def _parse_titles(xml_text: str, max_hours: int = 24) -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_hours)
    titles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    for item in root.findall(".//item"):
        pub = item.findtext("pubDate") or ""
        try:
            if parsedate_to_datetime(pub) < cutoff:
                continue
        except Exception:
            pass
        t = item.findtext("title") or ""
        if t:
            titles.append(t.strip())
    return titles


async def _fetch(client: httpx.AsyncClient, query: str) -> list[str]:
    try:
        r = await client.get(
            GNEWS_URL,
            params={**GNEWS_PARAMS, "q": query},
            timeout=10,
            follow_redirects=True,
        )
        r.raise_for_status()
        return _parse_titles(r.text)
    except Exception:
        return []


def _geocode(title: str) -> tuple[float, float] | None:
    """Busca nombre de ciudad en el título y retorna coords aproximadas."""
    from regions.city_graph import CITY_NODES, CITY_LABELS
    t = title.lower()
    # Más largo primero para evitar matches parciales
    for key, label in sorted(CITY_LABELS.items(), key=lambda x: -len(x[1])):
        if label.lower() in t and key in CITY_NODES:
            return CITY_NODES[key]
    return None


def _estado_coords(title: str) -> tuple[float, float] | None:
    """Fallback: busca nombre de estado."""
    _ESTADOS = {
        "aguascalientes": (21.88, -102.30), "baja california": (30.84, -115.28),
        "baja california sur": (25.19, -111.63), "campeche": (18.93, -90.53),
        "chiapas": (16.75, -93.11), "chihuahua": (28.63, -106.07),
        "coahuila": (27.06, -101.71), "colima": (19.24, -103.72),
        "durango": (24.02, -104.66), "guanajuato": (21.02, -101.26),
        "guerrero": (17.43, -100.00), "hidalgo": (20.12, -98.73),
        "jalisco": (20.68, -103.35), "estado de mexico": (19.29, -99.66),
        "michoacan": (19.70, -101.19), "morelos": (18.68, -99.10),
        "nayarit": (21.50, -104.90), "nuevo leon": (25.68, -100.32),
        "oaxaca": (17.06, -96.72), "puebla": (19.04, -98.20),
        "queretaro": (20.60, -100.39), "quintana roo": (21.16, -86.85),
        "san luis potosi": (22.15, -100.98), "sinaloa": (24.80, -107.40),
        "sonora": (29.07, -110.97), "tabasco": (17.99, -92.93),
        "tamaulipas": (23.74, -99.15), "tlaxcala": (19.31, -98.24),
        "veracruz": (19.20, -96.13), "yucatan": (20.97, -89.62),
        "zacatecas": (22.77, -102.58), "cdmx": (19.43, -99.13),
    }
    t = title.lower()
    import unicodedata
    def norm(s):
        n = unicodedata.normalize("NFKD", s)
        return "".join(c for c in n if not unicodedata.combining(c)).lower()
    t_norm = norm(t)
    for estado, coords in sorted(_ESTADOS.items(), key=lambda x: -len(x[0])):
        if norm(estado) in t_norm:
            return coords
    return None


async def get_robbery_news_nacional() -> list[dict]:
    """
    Consulta Google News por robos a transporte de carga.
    Geocodifica la ubicación desde el título de la noticia.
    Retorna lista de alertas listas para guardar en incidentes_historico.
    """
    async with httpx.AsyncClient() as client:
        generales, oficiales = await asyncio.gather(
            _fetch(client, _KW_ROBOS),
            _fetch(client, _KW_OFICIAL),
        )

    seen: set[str] = set()
    alertas: list[dict] = []

    for title, es_oficial in [(t, True) for t in oficiales] + [(t, False) for t in generales]:
        key = title[:50]
        if key in seen:
            continue
        seen.add(key)

        coords = _geocode(title) or _estado_coords(title)
        h = hashlib.md5(title[:80].encode()).hexdigest()[:12]

        alertas.append({
            "tipo":           "Robo a transportista",
            "emoji":          "🚨",
            "descripcion":    title,
            "severidad":      3 if es_oficial else 2,
            "fuente":         "GoogleNews-Robos",
            "hora":           None,
            "coords":         coords,
            "cierre_hash":    None,
            "tweet_hash":     h,
        })

    alertas.sort(key=lambda x: -x["severidad"])
    return alertas[:15]
