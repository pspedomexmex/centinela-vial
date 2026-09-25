"""
Cosechador de datos viales para dataset de tesis.
Escanea las 55 ciudades del grafo 3 veces al día (06:00, 14:00, 22:00 MX).
Sin envío a Telegram — solo acumulación en Supabase.

Tablas que alimenta:
  clima_historico     — temperatura, lluvia, viento, visibilidad por ciudad/hora
  flujo_historico     — velocidad actual vs libre por ciudad/hora
  incidentes_historico — accidentes y cierres en toda la red federal
"""
import os
import sys
import asyncio
import logging
import hashlib
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from regions.city_graph import CITY_NODES
from sources.tomtom_incidents import (
    _fetch_tile, _es_significativo, _to_alerta,
)

# Grid 2° × 2° sobre México — 144 tiles, cobertura nacional completa
# Lat 15–31°N, Lon -87 a -117°W
MEXICO_GRID: list[tuple[float, float]] = [
    (lat, lon)
    for lat in range(15, 32, 2)          # 9 latitudes: 15,17,19,21,23,25,27,29,31
    for lon in range(-117, -86, 2)       # 16 longitudes: -117…-87
]
from sources.robbery_news import get_robbery_news_nacional
from db.supabase_client import (
    registrar_incidentes_historico,
    registrar_clima_historico,
    registrar_flujo_historico,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOMTOM_KEY   = os.environ.get("TOMTOM_KEY", "")
OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"
FLOW_URL      = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"

_CONF_MINIMA = 0.5

_WMO: dict[int, tuple[str, bool]] = {
    0:  ("Despejado",                 False),
    1:  ("Mayormente despejado",      False),
    2:  ("Parcialmente nublado",      False),
    3:  ("Nublado",                   False),
    45: ("Niebla",                    True),
    48: ("Niebla con escarcha",       True),
    51: ("Llovizna ligera",           False),
    53: ("Llovizna moderada",         False),
    55: ("Llovizna intensa",          True),
    61: ("Lluvia ligera",             False),
    63: ("Lluvia moderada",           False),
    65: ("Lluvia intensa",            True),
    71: ("Nevada ligera",             True),
    73: ("Nevada moderada",           True),
    75: ("Nevada intensa",            True),
    77: ("Granizo",                   True),
    80: ("Chubascos ligeros",         False),
    81: ("Chubascos moderados",       False),
    82: ("Chubascos intensos",        True),
    85: ("Chubascos de nieve",        True),
    86: ("Chubascos de nieve intensos", True),
    95: ("Tormenta eléctrica",        True),
    96: ("Tormenta con granizo",      True),
    99: ("Tormenta con granizo intenso", True),
}


async def _fetch_clima(client: httpx.AsyncClient, ciudad: str, lat: float, lon: float) -> dict | None:
    try:
        r = await client.get(
            OPENMETEO_URL,
            params={
                "latitude":        lat,
                "longitude":       lon,
                "current":         "temperature_2m,precipitation,weather_code,wind_speed_10m,visibility",
                "timezone":        "America/Mexico_City",
                "wind_speed_unit": "kmh",
            },
            timeout=12,
        )
        r.raise_for_status()
        wx = r.json().get("current", {})
        if not wx:
            return None

        code        = int(wx.get("weather_code", 0) or 0)
        desc, severo = _WMO.get(code, ("Desconocido", False))

        return {
            "ciudad":        ciudad,
            "lat":           lat,
            "lon":           lon,
            "codigo_wmo":    code,
            "descripcion":   desc,
            "temperatura":   wx.get("temperature_2m"),
            "precipitacion": wx.get("precipitation"),
            "viento_kmh":    wx.get("wind_speed_10m"),
            "visibilidad_m": wx.get("visibility"),
            "es_severo":     severo,
        }
    except Exception:
        return None


async def _fetch_flujo(client: httpx.AsyncClient, ciudad: str, lat: float, lon: float) -> dict | None:
    if not TOMTOM_KEY:
        return None
    try:
        r = await client.get(
            FLOW_URL,
            params={"key": TOMTOM_KEY, "point": f"{lat},{lon}", "unit": "KMPH"},
            timeout=10,
        )
        r.raise_for_status()
        flow = r.json().get("flowSegmentData", {})
        if not flow:
            return None

        current  = float(flow.get("currentSpeed", 0) or 0)
        freeflow = float(flow.get("freeFlowSpeed", 0) or 0)
        conf     = float(flow.get("confidence", 0) or 0)

        if freeflow == 0 or conf < _CONF_MINIMA:
            return None

        ratio = current / freeflow
        nivel = "MUY_LENTO" if ratio < 0.40 else ("LENTO" if ratio < 0.65 else "NORMAL")

        return {
            "ciudad":           ciudad,
            "velocidad_actual": round(current, 1),
            "velocidad_libre":  round(freeflow, 1),
            "ratio_flujo":      round(ratio, 3),
            "nivel":            nivel,
        }
    except Exception:
        return None


async def harvest_clima_y_flujo() -> tuple[list[dict], list[dict]]:
    """Consulta clima y flujo en paralelo para las 55 ciudades."""
    cities = list(CITY_NODES.items())

    async with httpx.AsyncClient(timeout=15) as client:
        clima_tasks = [_fetch_clima(client, c, lat, lon) for c, (lat, lon) in cities]
        flujo_tasks = [_fetch_flujo(client, c, lat, lon) for c, (lat, lon) in cities]

        clima_results, flujo_results = await asyncio.gather(
            asyncio.gather(*clima_tasks),
            asyncio.gather(*flujo_tasks),
        )

    clima_recs = [r for r in clima_results if r]
    flujo_recs = [r for r in flujo_results if r]

    logger.info(f"Clima: {len(clima_recs)}/{len(cities)} ciudades OK")
    logger.info(f"Flujo: {len(flujo_recs)}/{len(cities)} ciudades OK")
    return clima_recs, flujo_recs


async def harvest_corredores() -> list[dict]:
    """
    Escanea el punto medio de cada arista del grafo.
    Filtra por la carretera exacta del tramo → datos precisos por corredor.
    Etiqueta cada incidente con _origen, _destino y _carretera para la BD.
    """
    if not TOMTOM_KEY:
        return []

    from regions.city_graph import CITY_EDGES, CITY_NODES

    # Aristas únicas (el grafo es bidireccional — evitar duplicados)
    vistos: set[frozenset] = set()
    tramos: list[dict] = []

    for city_a, vecinos in CITY_EDGES.items():
        for city_b, highway in vecinos.items():
            key = frozenset([city_a, city_b])
            if key in vistos:
                continue
            vistos.add(key)

            coords_a = CITY_NODES.get(city_a)
            coords_b = CITY_NODES.get(city_b)
            if not coords_a or not coords_b:
                continue

            tramos.append({
                "city_a":  city_a,
                "city_b":  city_b,
                "highway": highway,
                "lat":     (coords_a[0] + coords_b[0]) / 2,
                "lon":     (coords_a[1] + coords_b[1]) / 2,
            })

    async with httpx.AsyncClient(timeout=10) as client:
        tile_results = await asyncio.gather(
            *[_fetch_tile(client, t["lat"], t["lon"]) for t in tramos]
        )

    seen: set[str] = set()
    incidents: list[dict] = []

    for tramo, tile_incs in zip(tramos, tile_results):
        allowed = {tramo["highway"]} if tramo["highway"] else None

        for inc in tile_incs:
            if not _es_significativo(inc):
                continue
            p     = inc.get("properties", {})
            roads = p.get("roadNumbers") or []

            if allowed and roads and not any(r in allowed for r in roads):
                continue

            alerta = _to_alerta(inc)
            key = hashlib.md5(
                f"{tramo['city_a']}|{tramo['city_b']}|{alerta['descripcion'][:60]}"
                .encode()
            ).hexdigest()[:12]

            if key not in seen:
                seen.add(key)
                alerta["_origen"]    = tramo["city_a"]
                alerta["_destino"]   = tramo["city_b"]
                alerta["_carretera"] = tramo["highway"]
                incidents.append(alerta)

    logger.info(f"Corredores: {len(tramos)} tramos escaneados → {len(incidents)} incidentes")
    return incidents


async def harvest_grid_nacional() -> list[dict]:
    """
    Escanea México completo con un grid de 144 tiles (2°×2°).
    Cobertura: desde Tijuana hasta Cancún, Matamoros hasta Tapachula.
    Sin filtro de carretera — captura todo incidente crítico en el país.
    """
    if not TOMTOM_KEY:
        logger.warning("TOMTOM_KEY no configurada — saltando grid nacional")
        return []

    async with httpx.AsyncClient(timeout=10) as client:
        tile_results = await asyncio.gather(
            *[_fetch_tile(client, lat, lon) for lat, lon in MEXICO_GRID]
        )

    seen: set[str] = set()
    incidents: list[dict] = []

    for tile_incs in tile_results:
        for inc in tile_incs:
            if not _es_significativo(inc):
                continue
            alerta = _to_alerta(inc)
            raw    = f"{alerta['tipo']}|{alerta['descripcion'][:80]}"
            h      = hashlib.md5(raw.encode()).hexdigest()[:12]
            if h not in seen:
                seen.add(h)
                incidents.append(alerta)

    logger.info(f"Grid nacional: {len(MEXICO_GRID)} tiles → {len(incidents)} incidentes")
    return incidents


async def main():
    logger.info("=== Harvest Centinela Vial — inicio ===")

    (clima_recs, flujo_recs), inc_recs, corredor_recs, robos_recs = await asyncio.gather(
        harvest_clima_y_flujo(),
        harvest_grid_nacional(),
        harvest_corredores(),
        get_robbery_news_nacional(),
    )

    if clima_recs:
        registrar_clima_historico(clima_recs)
    if flujo_recs:
        registrar_flujo_historico(flujo_recs)
    if inc_recs:
        registrar_incidentes_historico(inc_recs)
    if corredor_recs:
        registrar_incidentes_historico(corredor_recs)
    if robos_recs:
        registrar_incidentes_historico(robos_recs)

    logger.info(
        f"=== Harvest completado: "
        f"{len(clima_recs)} clima | "
        f"{len(flujo_recs)} flujo | "
        f"{len(inc_recs)} grid | "
        f"{len(corredor_recs)} corredores | "
        f"{len(robos_recs)} robos ==="
    )


if __name__ == "__main__":
    asyncio.run(main())
