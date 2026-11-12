"""
TomTom Traffic Flow Segment Data API v4.
Detecta tramos con velocidad significativamente menor a la velocidad libre
en cada ciudad del path de la ruta — complementa los incidentes puntuales
con el estado general del flujo en el corredor.
Usa el mismo TOMTOM_KEY que incidents.
"""
import os
import httpx
import asyncio

TOMTOM_KEY = os.environ.get("TOMTOM_KEY", "")
FLOW_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"

# Relación velocidad_actual / velocidad_libre para reportar
_UMBRAL_LENTO     = 0.65   # <65 % → lento
_UMBRAL_MUY_LENTO = 0.40   # <40 % → muy lento / casi parado
_CONF_MINIMA      = 0.5    # descartar datos con baja confianza


async def _fetch_flow(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    try:
        r = await client.get(
            FLOW_URL,
            params={"key": TOMTOM_KEY, "point": f"{lat},{lon}", "unit": "KMPH"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("flowSegmentData", {})
    except Exception:
        return {}


async def get_flow_speeds_dict(city_keys: list[str]) -> dict[str, float]:
    """
    Consulta TomTom Flow para las ciudades indicadas.
    Retorna {city_key: velocidad_actual_kmh} solo donde hay datos confiables.
    """
    if not TOMTOM_KEY or not city_keys:
        return {}
    from regions.city_graph import CITY_NODES
    points = [(k, *CITY_NODES[k]) for k in city_keys if k in CITY_NODES]
    if not points:
        return {}
    async with httpx.AsyncClient(timeout=12) as client:
        results = await asyncio.gather(
            *[_fetch_flow(client, lat, lon) for _, lat, lon in points]
        )
    speeds: dict[str, float] = {}
    for (key, _, _), flow in zip(points, results):
        if not flow:
            continue
        current = flow.get("currentSpeed", 0) or 0
        conf    = flow.get("confidence", 0) or 0
        if current > 0 and conf >= _CONF_MINIMA:
            speeds[key] = float(current)
    return speeds


async def get_flow_alerts_for_city_route(city_path: list[str]) -> list[dict]:
    """
    Consulta el flujo de tráfico en cada ciudad intermedia del path.
    Devuelve alertas solo donde la velocidad cae por debajo de los umbrales.
    """
    if not TOMTOM_KEY or not city_path:
        return []

    from regions.city_graph import get_route_segments, CITY_LABELS

    segments = get_route_segments(city_path)
    if not segments:
        return []

    points = [(city, lat, lon) for city, lat, lon, _ in segments]

    async with httpx.AsyncClient(timeout=12) as client:
        results = await asyncio.gather(
            *[_fetch_flow(client, lat, lon) for _, lat, lon in points]
        )

    alertas: list[dict] = []
    for (city, _, _), flow in zip(points, results):
        if not flow:
            continue
        current   = flow.get("currentSpeed", 0) or 0
        freeflow  = flow.get("freeFlowSpeed", 0) or 0
        conf      = flow.get("confidence", 0) or 0

        if freeflow == 0 or conf < _CONF_MINIMA:
            continue

        ratio = current / freeflow

        if ratio < _UMBRAL_MUY_LENTO:
            emoji, nivel, sev = "🔴", "Muy lento", 8
        elif ratio < _UMBRAL_LENTO:
            emoji, nivel, sev = "🟡", "Lento", 5
        else:
            continue

        label = CITY_LABELS.get(city, city)
        pct   = int((1 - ratio) * 100)
        alertas.append({
            "tipo":        f"Flujo {nivel.lower()}",
            "emoji":       emoji,
            "descripcion": (
                f"{nivel} cerca de {label}: "
                f"{int(current)} km/h — {pct}% por debajo de lo normal"
            ),
            "severidad":   sev,
            "fuente":      "TomTom Flow",
            "hora":        None,
        })

    alertas.sort(key=lambda x: x["severidad"], reverse=True)
    return alertas


async def get_flow_alerts_for_regions(region_keys: list[str]) -> list[dict]:
    """Fallback cuando no hay city_path: consulta tile ancla de cada región."""
    if not TOMTOM_KEY or not region_keys:
        return []

    from sources.tomtom_incidents import REGION_ANCHOR
    from regions.mexico_regions import REGIONS

    points = [
        (key, *REGION_ANCHOR[key])
        for key in region_keys
        if key in REGION_ANCHOR
    ]
    if not points:
        return []

    async with httpx.AsyncClient(timeout=12) as client:
        results = await asyncio.gather(
            *[_fetch_flow(client, lat, lon) for _, lat, lon in points]
        )

    alertas: list[dict] = []
    for (key, _, _), flow in zip(points, results):
        if not flow:
            continue
        current  = flow.get("currentSpeed", 0) or 0
        freeflow = flow.get("freeFlowSpeed", 0) or 0
        conf     = flow.get("confidence", 0) or 0
        if freeflow == 0 or conf < _CONF_MINIMA:
            continue
        ratio = current / freeflow
        if ratio < _UMBRAL_MUY_LENTO:
            emoji, nivel, sev = "🔴", "Muy lento", 8
        elif ratio < _UMBRAL_LENTO:
            emoji, nivel, sev = "🟡", "Lento", 5
        else:
            continue
        nombre = REGIONS.get(key, {}).get("nombre", key)
        pct    = int((1 - ratio) * 100)
        alertas.append({
            "tipo":        f"Flujo {nivel.lower()}",
            "emoji":       emoji,
            "descripcion": f"{nivel} en {nombre}: {int(current)} km/h ({pct}% bajo lo normal)",
            "severidad":   sev,
            "fuente":      "TomTom Flow",
            "hora":        None,
        })

    alertas.sort(key=lambda x: x["severidad"], reverse=True)
    return alertas
