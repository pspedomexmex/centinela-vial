"""
Incidentes de tráfico via TomTom Traffic Incidents API v5.
Reemplaza la integración de Waze (bloqueada).
Requiere TOMTOM_KEY en variables de entorno.
"""
import os
import httpx
import asyncio
from typing import Optional

TOMTOM_KEY = os.environ.get("TOMTOM_KEY", "")
TOMTOM_URL = "https://api.tomtom.com/traffic/services/5/incidentDetails"

# Máximo bbox permitido por TomTom: ~10,000 km² → usamos tiles de 0.7°×0.7°
TILE_HALF = 0.35

# Tiles (lat, lon) de ciudades clave por región — cubre los corredores principales
REGION_TILES: dict[str, list[tuple[float, float]]] = {
    "noroeste":    [(29.1, -110.9), (24.8, -107.4), (23.2, -106.4)],
    "norte":       [(28.6, -106.1), (25.5, -103.4), (24.0, -104.7)],
    "noreste":     [(25.7, -100.3), (25.4, -101.0), (22.2, -100.9)],
    "occidente":   [(20.7, -103.4), (19.7, -101.2)],
    "centro_norte":[(20.6, -100.4), (21.1, -101.7), (21.9, -102.3)],
    "centro":      [(19.4,  -99.1), (19.0,  -98.2), (19.3,  -99.7)],
    "golfo":       [(19.2,  -96.1), (18.0,  -92.9), (17.1,  -96.7)],
    "peninsula":   [(20.9,  -89.6), (21.2,  -86.8)],
}

CATEGORIA = {
    0:  ("⚠️",  "Incidente"),
    1:  ("🚨",  "Accidente"),
    2:  ("🌫️", "Niebla"),
    3:  ("⚠️",  "Condiciones peligrosas"),
    4:  ("🌧️", "Lluvia"),
    5:  ("🧊",  "Hielo"),
    6:  ("🚗",  "Tráfico"),
    7:  ("🚧",  "Carril cerrado"),
    8:  ("🚧",  "Carretera cerrada"),
    9:  ("🏗️", "Obras"),
    10: ("💨",  "Viento"),
    11: ("🌊",  "Inundación"),
    14: ("🚘",  "Vehículo averiado"),
}

# Categorías que siempre se reportan sin importar la demora
CATEGORIAS_CRITICAS = {1, 3, 8, 11}


def _bbox(lat: float, lon: float) -> str:
    return f"{lon - TILE_HALF},{lat - TILE_HALF},{lon + TILE_HALF},{lat + TILE_HALF}"


async def _fetch_tile(client: httpx.AsyncClient, lat: float, lon: float) -> list[dict]:
    params = {
        "key": TOMTOM_KEY,
        "bbox": _bbox(lat, lon),
        "fields": "{incidents{type,geometry{type,coordinates},properties{iconCategory,magnitudeOfDelay,from,to,length,roadNumbers}}}",
        "language": "es-ES",
        "timeValidityFilter": "present",
    }
    try:
        r = await client.get(TOMTOM_URL, params=params)
        r.raise_for_status()
        return r.json().get("incidents", [])
    except Exception:
        return []


def _es_significativo(inc: dict) -> bool:
    p = inc.get("properties", {})
    cat = p.get("iconCategory", 0)
    delay = p.get("magnitudeOfDelay", 0)
    if cat in CATEGORIAS_CRITICAS:
        return True
    return delay >= 3  # mayor o indefinido (cierre)


def _to_alerta(inc: dict) -> dict:
    p = inc.get("properties", {})
    cat = p.get("iconCategory", 0)
    delay = p.get("magnitudeOfDelay", 0)
    emoji, nombre = CATEGORIA.get(cat, ("⚠️", "Incidente"))
    desde = p.get("from", "")
    hasta = p.get("to", "")
    roads = ", ".join(p.get("roadNumbers", []))
    desc_parts = [nombre]
    if roads:
        desc_parts.append(f"en {roads}")
    if desde and hasta:
        desc_parts.append(f"({desde} → {hasta})")
    elif desde:
        desc_parts.append(f"en {desde}")
    return {
        "tipo": nombre,
        "emoji": emoji,
        "descripcion": " ".join(desc_parts),
        "severidad": delay,
        "fuente": "TomTom",
    }


async def get_incidents_for_region(region_key: str) -> list[dict]:
    if not TOMTOM_KEY:
        return []
    tiles = REGION_TILES.get(region_key, [])
    if not tiles:
        return []

    async with httpx.AsyncClient(timeout=10) as client:
        tasks = [_fetch_tile(client, lat, lon) for lat, lon in tiles]
        results = await asyncio.gather(*tasks)

    seen: set[str] = set()
    incidents: list[dict] = []
    for tile_incs in results:
        for inc in tile_incs:
            if not _es_significativo(inc):
                continue
            p = inc.get("properties", {})
            key = f"{p.get('from','')}-{p.get('to','')}-{p.get('iconCategory',0)}"
            if key in seen:
                continue
            seen.add(key)
            incidents.append(_to_alerta(inc))

    incidents.sort(key=lambda x: x["severidad"], reverse=True)
    return incidents[:8]  # máx 8 por región


async def get_incidents_for_regions(region_keys: list[str]) -> tuple[list[dict], list[str]]:
    """
    Retorna (incidents, errors).
    errors contiene mensajes si algo falla, para mostrar al usuario.
    """
    if not TOMTOM_KEY:
        return [], ["⚙️ TOMTOM_KEY no configurada"]

    tasks = [get_incidents_for_region(r) for r in region_keys]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    combined: list[dict] = []
    errors: list[str] = []
    for r in results:
        if isinstance(r, Exception):
            errors.append(f"Error consultando TomTom: {r}")
        else:
            combined.extend(r)

    combined.sort(key=lambda x: x["severidad"], reverse=True)
    return combined, errors
