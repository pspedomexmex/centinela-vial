"""
Monitor de noticias sobre la Resistencia Civil Pacífica Nacional (RCPN).
Fuente: Google News RSS. Sin API key. Ventana de 30 días.
"""
import asyncio
import hashlib
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

GNEWS_URL    = "https://news.google.com/rss/search"
GNEWS_PARAMS = {"hl": "es-419", "gl": "MX", "ceid": "MX:es-419"}

DIAS_RECIENTE = 2
DIAS_SEMANA   = 8
MAX_DIAS      = 30

_MESES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]

_GNEWS_QUERIES: list[tuple[str, str]] = [
    ('"Resistencia Civil Pacífica Nacional"',          "Google News"),
    ('resistencia civil pacífica México 2026',         "Google News"),
]

_CLASIFICACION: list[tuple[tuple[str, str], list[str]]] = [
    (("🚨", "Represión"),      ["detenido", "detención", "represión", "agresión",
                                 "violencia", "arrestado", "preso", "muertos", "heridos"]),
    (("✅", "Logro"),          ["victoria", "logro", "ganó", "revocó", "aprobó", "triunfo"]),
    (("🚶", "Movilización"),   ["marcha", "manifestación", "plantón", "concentración",
                                 "mitin", "convocatoria", "movilización", "bloqueo", "cierre"]),
    (("⚖️", "Legal/Político"), ["demanda", "amparo", "juicio", "resolución", "electoral",
                                 "voto", "ine", "tribunal", "fraude"]),
    (("📢", "Declaración"),    ["declaró", "anunció", "exige", "denuncia", "comunicado"]),
]

_KW_EXCLUIR_DESASTRE = ["huracán", "hurricane", "tormenta tropical", "ciclón"]
_KW_MORENA           = ["regeneración nacional", "movimiento de regeneración",
                         "andrés manuel", "lópez obrador", "amlo",
                         "cuarta transformación", "morena celebra", "morena gana",
                         "claudia sheinbaum"]
_KW_RESISTENCIA      = ["resistencia", "marcha", "protesta", "plantón",
                         "manifestación", "rcpn", "bloqueo", "convocatoria"]


def _excluir(titulo: str) -> bool:
    t = titulo.lower()
    if any(k in t for k in _KW_EXCLUIR_DESASTRE):
        return True
    if any(k in t for k in _KW_MORENA):
        return not any(k in t for k in _KW_RESISTENCIA)
    return False


def _clasificar(texto: str) -> tuple[str, str]:
    t = texto.lower()
    for (emoji, tipo), kws in _CLASIFICACION:
        if any(k in t for k in kws):
            return emoji, tipo
    return "📰", "Noticia"


def _fmt_fecha(dt: datetime) -> str:
    mx = dt.astimezone(timezone(timedelta(hours=-6)))
    return f"{mx.day} {_MESES[mx.month - 1]}"


def _parse_gnews(xml_text: str, fuente_default: str = "Google News") -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_DIAS)
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
        link  = (item.findtext("link")  or "").strip()
        if not title:
            continue
        src_el = item.find("source")
        fuente = (src_el.text or fuente_default).strip() if src_el is not None else fuente_default
        items.append({"title": title, "link": link, "fuente": fuente, "dt": dt})
    return items


async def _fetch(client: httpx.AsyncClient, query: str, fuente: str) -> list[dict]:
    try:
        r = await client.get(
            GNEWS_URL,
            params={**GNEWS_PARAMS, "q": query},
            timeout=8.0,
            follow_redirects=True,
        )
        r.raise_for_status()
        return _parse_gnews(r.text, fuente_default=fuente)
    except Exception:
        return []


async def get_rcpn_noticias() -> list[dict]:
    async with httpx.AsyncClient() as client:
        lotes = await asyncio.gather(*[
            _fetch(client, q, label) for q, label in _GNEWS_QUERIES
        ])

    seen: set[str] = set()
    noticias: list[dict] = []
    for lote in lotes:
        for item in lote:
            if _excluir(item["title"]):
                continue
            key = item["title"][:50]
            if key in seen:
                continue
            seen.add(key)
            emoji, tipo = _clasificar(item["title"])
            noticias.append({
                "titulo": item["title"],
                "link":   item["link"],
                "fuente": item["fuente"],
                "emoji":  emoji,
                "tipo":   tipo,
                "fecha":  _fmt_fecha(item["dt"]),
                "dt":     item["dt"],
                "hash":   hashlib.md5(item["title"][:80].encode()).hexdigest()[:12],
            })

    noticias.sort(key=lambda x: x["dt"], reverse=True)
    return noticias[:25]
