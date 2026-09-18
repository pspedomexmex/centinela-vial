"""
Obtiene incidentes de Waze via su API no oficial (Livemap).
No requiere API key — usa el endpoint público de Waze.
"""
import httpx
import asyncio
from typing import Optional


WAZE_URL = "https://www.waze.com/live-map/api/georss"

TIPO_INCIDENTE = {
    "ACCIDENT": ("🚨", "Accidente"),
    "JAM": ("🚗", "Tráfico"),
    "ROAD_CLOSED": ("🚧", "Carretera cerrada"),
    "HAZARD": ("⚠️", "Peligro"),
    "POLICE": ("👮", "Policía / Retén"),
    "CONSTRUCTION": ("🏗️", "Construcción"),
}

# Bounding boxes aproximados por región de México
REGION_BBOX = {
    "noroeste":    {"bottom": 22.5, "top": 32.7, "left": -117.1, "right": -108.0},
    "norte":       {"bottom": 24.0, "top": 31.8, "left": -108.0, "right": -98.5},
    "noreste":     {"bottom": 22.0, "top": 27.5, "left": -100.5, "right": -96.5},
    "occidente":   {"bottom": 18.5, "top": 23.5, "left": -105.5, "right": -99.5},
    "centro_norte":{"bottom": 20.5, "top": 24.5, "left": -103.0, "right": -98.5},
    "centro":      {"bottom": 18.5, "top": 20.5, "left": -100.5, "right": -97.5},
    "golfo":       {"bottom": 14.5, "top": 22.5, "left": -97.0,  "right": -90.5},
    "peninsula":   {"bottom": 17.5, "top": 21.5, "left": -90.5,  "right": -86.5},
}


async def get_incidents_for_region(region_key: str) -> list[dict]:
    bbox = REGION_BBOX.get(region_key)
    if not bbox:
        return []

    params = {
        "bottom": bbox["bottom"],
        "top": bbox["top"],
        "left": bbox["left"],
        "right": bbox["right"],
        "env": "row",
        "types": "alerts,jams",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(WAZE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    incidents = []

    # Alertas (accidentes, peligros, policía)
    for alert in data.get("alerts", []):
        tipo = alert.get("type", "HAZARD")
        subtipo = alert.get("subtype", "")
        emoji, nombre = TIPO_INCIDENTE.get(tipo, ("⚠️", tipo))
        street = alert.get("street") or alert.get("city") or "Carretera"
        city = alert.get("city", "")
        incidents.append({
            "tipo": nombre,
            "emoji": emoji,
            "descripcion": f"{nombre} en {street}, {city}".strip(", "),
            "lat": alert.get("location", {}).get("y"),
            "lng": alert.get("location", {}).get("x"),
            "severidad": alert.get("reportRating", 0),
            "fuente": "Waze",
        })

    # Atascos severos
    for jam in data.get("jams", []):
        if jam.get("level", 0) >= 4:  # 4-5 = severo
            street = jam.get("street") or jam.get("city") or "Carretera"
            city = jam.get("city", "")
            delay = jam.get("delay", 0)
            incidents.append({
                "tipo": "Tráfico severo",
                "emoji": "🔴",
                "descripcion": f"Tráfico severo en {street}, {city} (+{delay//60} min)".strip(", "),
                "lat": None,
                "lng": None,
                "severidad": jam.get("level", 0),
                "fuente": "Waze",
            })

    return incidents


async def get_incidents_for_regions(region_keys: list[str]) -> list[dict]:
    tasks = [get_incidents_for_region(r) for r in region_keys]
    results = await asyncio.gather(*tasks)
    combined = []
    for r in results:
        combined.extend(r)
    # Ordenar por severidad desc
    combined.sort(key=lambda x: x.get("severidad", 0), reverse=True)
    return combined
