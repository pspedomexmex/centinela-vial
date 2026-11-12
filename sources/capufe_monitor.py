"""
Monitoreo de CAPUFE / SCT.
Scraping del feed RSS oficial y portal CAPUFE.
"""
import httpx
import xml.etree.ElementTree as ET
import asyncio
import re


CAPUFE_RSS = "https://www.capufe.gob.mx/site/xml/noticias.xml"
SCT_RSS = "https://www.sct.gob.mx/comunicacion-social/noticias/feed/"

# Palabras clave que indican un incidente relevante para carga
KEYWORDS_CRITICOS = [
    "accidente", "cierre", "bloqueo", "manifestación", "manifestacion",
    "derrumbe", "inundación", "inundacion", "neblina", "granizo",
    "viento", "niebla", "interrupción", "interrupcion", "paro",
    "retén", "reten", "operativo", "revisión", "revision",
]


def _relevante(texto: str) -> bool:
    texto_lower = texto.lower()
    return any(k in texto_lower for k in KEYWORDS_CRITICOS)


async def _fetch_rss(url: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
    except Exception:
        return []

    items = []
    for item in root.findall(".//item"):
        titulo = item.findtext("title", "")
        desc = item.findtext("description", "")
        link = item.findtext("link", "")
        fecha = item.findtext("pubDate", "")

        texto_completo = f"{titulo} {desc}"
        if _relevante(texto_completo):
            items.append({
                "titulo": titulo,
                "descripcion": re.sub(r"<[^>]+>", "", desc)[:200],
                "link": link,
                "fecha": fecha,
                "fuente": "CAPUFE/SCT",
                "emoji": "🛣️",
            })
    return items


async def get_capufe_alerts() -> list[dict]:
    tasks = [_fetch_rss(CAPUFE_RSS), _fetch_rss(SCT_RSS)]
    results = await asyncio.gather(*tasks)
    combined = []
    for r in results:
        combined.extend(r)
    return combined


async def get_capufe_alerts_for_regions(region_keys: list[str], region_data: dict) -> list[dict]:
    """Filtra alertas de CAPUFE que mencionan estados de las regiones activas."""
    all_alerts = await get_capufe_alerts()
    if not all_alerts:
        return []

    # Obtener estados relevantes
    relevant_terms = set()
    for rk in region_keys:
        rinfo = region_data.get(rk, {})
        for estado in rinfo.get("estados", []):
            relevant_terms.add(estado.lower())
        for kw in rinfo.get("keywords", []):
            relevant_terms.add(kw.lower())

    filtered = []
    for alert in all_alerts:
        texto = f"{alert['titulo']} {alert['descripcion']}".lower()
        if any(term in texto for term in relevant_terms):
            filtered.append(alert)

    return filtered
