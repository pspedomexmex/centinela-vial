"""
Incidentes de tráfico via TomTom Traffic Incidents API v5.
Reemplaza la integración de Waze (bloqueada).
Requiere TOMTOM_KEY en variables de entorno.
"""
import os
import httpx
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

# UTC-6 (hora del centro de México, sin ajuste DST — suficiente precisión para alertas)
_TZ_MX = timezone(timedelta(hours=-6))

TOMTOM_KEY = os.environ.get("TOMTOM_KEY", "")
TOMTOM_URL = "https://api.tomtom.com/traffic/services/5/incidentDetails"

# Máximo bbox permitido por TomTom: ~10,000 km² → usamos tiles de 0.7°×0.7°
TILE_HALF = 0.35

# Tiles (lat, lon) de ciudades clave por región — usados en /alertas sin viaje activo
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

# Tile ancla (1 punto representativo por región) para cubrir origen/destino
REGION_ANCHOR: dict[str, tuple[float, float]] = {
    "noroeste":     (29.1, -110.9),  # Hermosillo
    "norte":        (28.6, -106.1),  # Chihuahua
    "noreste":      (25.7, -100.3),  # Monterrey
    "occidente":    (20.7, -103.4),  # Guadalajara
    "centro_norte": (20.6, -100.4),  # Querétaro
    "centro":       (19.4,  -99.1),  # CDMX
    "golfo":        (19.2,  -96.1),  # Veracruz
    "peninsula":    (20.9,  -89.6),  # Mérida
}

# Tiles de corredor para cada par de regiones adyacentes — enfocados en el eje
# de las carreteras federales reales que usan los camiones de carga.
# Clave: frozenset de las dos regiones. Valores: tiles a lo largo del corredor.
CORRIDOR_TILES: dict[frozenset, list[tuple[float, float]]] = {
    # MEX-57D: CDMX ↔ Querétaro
    frozenset({"centro", "centro_norte"}): [
        (20.0, -99.9),   # San Juan del Río
        (19.7, -99.6),   # Tepeji del Río
        (20.6, -100.4),  # Querétaro
    ],
    # MEX-57: SLP ↔ Monterrey (vía Matehuala)
    frozenset({"centro_norte", "noreste"}): [
        (21.8, -100.7),  # SLP norte
        (23.1, -100.1),  # Matehuala
        (24.2, -100.5),  # Huizache / Los Rayones
    ],
    # MEX-15D: CDMX ↔ Morelia/Maravatío
    frozenset({"centro", "occidente"}): [
        (19.5, -100.1),  # Lerma / Toluca
        (19.7, -100.7),  # Atlacomulco
        (19.7, -101.2),  # Maravatío
    ],
    # MEX-80: Guadalajara ↔ León/Aguascalientes
    frozenset({"occidente", "centro_norte"}): [
        (20.7, -103.4),  # Guadalajara norte
        (20.9, -102.3),  # Lagos de Moreno
        (21.1, -101.7),  # León / Silao
    ],
    # MEX-45: Zacatecas ↔ Durango
    frozenset({"centro_norte", "norte"}): [
        (22.0, -102.3),  # Zacatecas
        (23.5, -102.7),  # Fresnillo
        (24.8, -103.9),  # Durango sur
    ],
    # MEX-40: Torreón ↔ Saltillo/Monterrey
    frozenset({"norte", "noreste"}): [
        (25.5, -103.4),  # Torreón
        (25.3, -101.5),  # Ramos Arizpe
        (25.4, -101.0),  # Saltillo
    ],
    # MEX-16: Hermosillo ↔ Chihuahua (Sierra Tarahumara)
    frozenset({"noroeste", "norte"}): [
        (29.1, -110.9),  # Hermosillo norte
        (28.0, -108.5),  # Puerto El Novillo / sierra
        (28.6, -107.0),  # Cuauhtémoc
    ],
    # MEX-15: Mazatlán ↔ Tepic (espinazo del diablo)
    frozenset({"noroeste", "occidente"}): [
        (24.8, -107.4),  # Culiacán
        (23.2, -106.4),  # Mazatlán / nudo Tepic
        (22.3, -105.9),  # Tepic sur
    ],
    # MEX-150D: Puebla ↔ Veracruz (Cumbres de Maltrata)
    frozenset({"centro", "golfo"}): [
        (19.0, -97.5),   # Orizaba / Córdoba
        (18.9, -97.1),   # Cumbres de Maltrata
        (19.2, -96.1),   # Veracruz
    ],
    # MEX-85: Tampico ↔ Cd. Valles / San Luis
    frozenset({"noreste", "golfo"}): [
        (23.0, -98.8),   # Ciudad Mante
        (22.2, -97.9),   # Tampico norte
        (21.0, -97.5),   # Poza Rica
    ],
    # MEX-186: Villahermosa ↔ Campeche/Mérida
    frozenset({"golfo", "peninsula"}): [
        (18.0, -92.9),   # Villahermosa
        (19.0, -91.0),   # Champotón
        (20.9, -89.6),   # Mérida entrada
    ],
}

# Carreteras federales relevantes para cada corredor.
# En get_incidents_for_route se acumulan los sets de todos los pares de la ruta
# y se descartan incidentes en carreteras que no pertenecen al corredor.
CORRIDOR_ROADS: dict[frozenset, set[str]] = {
    frozenset({"centro", "centro_norte"}):   {"MEX-57D", "MEX-57", "MEX-45D"},
    frozenset({"centro_norte", "noreste"}):  {"MEX-57D", "MEX-57"},
    frozenset({"centro", "occidente"}):      {"MEX-15D", "MEX-15"},
    frozenset({"occidente", "centro_norte"}):{"MEX-80", "MEX-90", "MEX-45"},
    frozenset({"centro_norte", "norte"}):    {"MEX-45", "MEX-45D", "MEX-49"},
    frozenset({"norte", "noreste"}):         {"MEX-40", "MEX-40D", "MEX-57"},
    frozenset({"noroeste", "norte"}):        {"MEX-16", "MEX-45"},
    frozenset({"noroeste", "occidente"}):    {"MEX-15", "MEX-15D"},
    frozenset({"centro", "golfo"}):          {"MEX-150D", "MEX-150", "MEX-85D", "MEX-85"},
    frozenset({"noreste", "golfo"}):         {"MEX-85", "MEX-85D", "MEX-180", "MEX-180D"},
    frozenset({"golfo", "peninsula"}):       {"MEX-186", "MEX-180", "MEX-261"},
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

# Categorías que NO se reportan bajo ninguna circunstancia
CATEGORIAS_IGNORADAS = {2, 4, 5, 6, 7, 9, 10, 14}
# 2=Niebla, 4=Lluvia, 5=Hielo, 6=Tráfico, 7=Carril cerrado
# 9=Obras, 10=Viento, 14=Vehículo averiado


def _bbox(lat: float, lon: float) -> str:
    return f"{lon - TILE_HALF},{lat - TILE_HALF},{lon + TILE_HALF},{lat + TILE_HALF}"


async def _fetch_tile(client: httpx.AsyncClient, lat: float, lon: float) -> list[dict]:
    params = {
        "key": TOMTOM_KEY,
        "bbox": _bbox(lat, lon),
        "fields": "{incidents{type,geometry{type,coordinates},properties{iconCategory,magnitudeOfDelay,startTime,from,to,length,roadNumbers}}}",
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
    if cat in CATEGORIAS_IGNORADAS:
        return False
    if cat not in CATEGORIAS_CRITICAS:
        return False
    # Cierres de carretera (cat 8): reportar aunque TomTom no asigne número MEX-XX.
    # El tile ya garantiza proximidad geográfica al corredor.
    if cat == 8:
        return True
    # Resto de categorías críticas: requerir número de carretera federal.
    return bool(p.get("roadNumbers"))


def _fmt_hora(iso: str | None) -> str | None:
    """'2024-01-15T20:30:00Z' → '14:30' (hora México UTC-6)"""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(_TZ_MX).strftime("%H:%M")
    except Exception:
        return None


def _to_alerta(inc: dict) -> dict:
    p = inc.get("properties", {})
    cat = p.get("iconCategory", 0)
    delay = p.get("magnitudeOfDelay", 0)
    emoji, nombre = CATEGORIA.get(cat, ("⚠️", "Incidente"))
    desde = p.get("from", "")
    hasta = p.get("to", "")
    roads = ", ".join(p.get("roadNumbers", []))
    hora = _fmt_hora(p.get("startTime"))
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
        "hora": hora,
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

    # Agrupar por número de carretera — máx 2 incidentes distintos por carretera
    road_count: dict[str, int] = {}
    seen_desc: set[str] = set()
    incidents: list[dict] = []

    for tile_incs in results:
        for inc in tile_incs:
            if not _es_significativo(inc):
                continue
            p = inc.get("properties", {})
            roads = tuple(sorted(p.get("roadNumbers") or []))
            road_key = ",".join(roads)
            if road_count.get(road_key, 0) >= 2:
                continue
            alerta = _to_alerta(inc)
            # Deduplicar por descripción resumida
            desc_key = alerta["descripcion"][:60]
            if desc_key in seen_desc:
                continue
            seen_desc.add(desc_key)
            road_count[road_key] = road_count.get(road_key, 0) + 1
            incidents.append(alerta)

    incidents.sort(key=lambda x: x["severidad"], reverse=True)
    return incidents[:6]  # máx 6 por región


async def get_incidents_for_route(region_path: list[str]) -> tuple[list[dict], list[str]]:
    """
    Consulta incidentes solo en los corredores de la ruta.
    Para cada par de regiones adyacentes usa CORRIDOR_TILES (eje de carretera real)
    más un tile ancla en origen y destino. Mucho menos ruido que región completa.
    Fallback a get_incidents_for_regions si la ruta tiene ≤1 región.
    """
    if not TOMTOM_KEY:
        return [], ["⚙️ TOMTOM_KEY no configurada"]
    if not region_path:
        return [], []
    if len(region_path) == 1:
        inc = await get_incidents_for_region(region_path[0])
        return inc, []

    tiles: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()

    def _add(t: tuple[float, float]):
        if t not in seen:
            seen.add(t)
            tiles.append(t)

    # Tiles ancla de origen y destino
    for r in (region_path[0], region_path[-1]):
        if r in REGION_ANCHOR:
            _add(REGION_ANCHOR[r])

    # Tiles de corredor por cada arista adyacente de la ruta
    for i in range(len(region_path) - 1):
        pair = frozenset({region_path[i], region_path[i + 1]})
        for t in CORRIDOR_TILES.get(pair, []):
            _add(t)

    # Un único set de carreteras válidas para toda la ruta regional
    allowed_roads: set[str] = set()
    for i in range(len(region_path) - 1):
        pair = frozenset({region_path[i], region_path[i + 1]})
        allowed_roads.update(CORRIDOR_ROADS.get(pair, set()))

    async with httpx.AsyncClient(timeout=10) as client:
        results = await asyncio.gather(*[_fetch_tile(client, lat, lon) for lat, lon in tiles])

    # Mismo filtro para todos los tiles (granularidad de región, no de ciudad)
    allowed_per_tile = [allowed_roads] * len(tiles) if allowed_roads else None
    incidents = _dedup_incidents(list(results), allowed_per_tile)
    return incidents[:10], []


def _dedup_incidents(
    all_tile_results: list[list[dict]],
    allowed_per_tile: list[set[str]] | None = None,
    city_labels: list[str] | None = None,
) -> list[dict]:
    """
    Consolida resultados de varios tiles en una lista deduplicada.
    - allowed_per_tile: highways válidas por tile (None = sin filtro de highway)
    - city_labels: nombre de ciudad por tile — se añade a cierres sin número MEX
    """
    road_count: dict[str, int] = {}
    seen_desc: set[str] = set()
    incidents: list[dict] = []

    for idx, tile_incs in enumerate(all_tile_results):
        tile_allowed = (allowed_per_tile[idx]
                        if allowed_per_tile and idx < len(allowed_per_tile)
                        else None)
        city_label = (city_labels[idx]
                      if city_labels and idx < len(city_labels)
                      else None)

        for inc in tile_incs:
            if not _es_significativo(inc):
                continue
            p = inc.get("properties", {})
            roads = p.get("roadNumbers") or []
            cat = p.get("iconCategory", 0)
            # Cierres (cat 8) sin número MEX: pasan por proximidad geográfica del tile.
            # Resto: filtrar por highway del corredor.
            if tile_allowed and roads and not any(r in tile_allowed for r in roads):
                continue
            road_key = ",".join(sorted(roads))
            if road_count.get(road_key, 0) >= 2:
                continue

            alerta = _to_alerta(inc)

            if cat == 8 and not roads:
                # Añadir ciudad para dar contexto geográfico
                if city_label:
                    alerta["descripcion"] += f" — cerca de {city_label}"
                # Deduplicar bidireccional: mismo par de calles sin importar dirección
                desde = p.get("from", "")[:35]
                hasta = p.get("to", "")[:35]
                desc_key = "cierre:" + "|".join(sorted([desde, hasta]))
            else:
                desc_key = alerta["descripcion"][:60]

            if desc_key in seen_desc:
                continue
            seen_desc.add(desc_key)
            road_count[road_key] = road_count.get(road_key, 0) + 1
            incidents.append(alerta)

    incidents.sort(key=lambda x: x["severidad"], reverse=True)
    return incidents


async def get_incidents_for_city_route(
    city_path: list[str],
) -> tuple[list[dict], list[str]]:
    """
    Algoritmo preciso: 1 tile por ciudad en el path, filtrado a las MEX-XX
    exactas de las aristas adyacentes (entrante + saliente).

    Para CDMX → Cd. Juárez (path: cdmx, queretaro, slp, zacatecas, durango,
    chihuahua, ciudad_juarez) consulta 6 tiles y filtra:
      - Querétaro tile  → solo MEX-57D
      - SLP tile        → MEX-57 + MEX-49
      - Zacatecas tile  → MEX-49 + MEX-45
      - Durango tile    → MEX-45
      - Chihuahua tile  → MEX-45
      - Cd. Juárez tile → MEX-45
    Resultado: 0 ruido de AGS, GDL ni ningún corredor ajeno a la ruta.
    """
    if not TOMTOM_KEY:
        return [], ["⚙️ TOMTOM_KEY no configurada"]
    if not city_path:
        return [], []

    from regions.city_graph import get_route_segments, CITY_LABELS

    segments = get_route_segments(city_path)
    if not segments:
        return [], []

    tiles          = [(lat, lon) for _, lat, lon, _ in segments]
    allowed_per_tile = [hw for _, _, _, hw in segments]
    city_labels    = [CITY_LABELS.get(city, city.title()) for city, _, _, _ in segments]

    async with httpx.AsyncClient(timeout=10) as client:
        results = await asyncio.gather(
            *[_fetch_tile(client, lat, lon) for lat, lon in tiles]
        )

    incidents = _dedup_incidents(list(results), allowed_per_tile, city_labels)
    return incidents[:10], []


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
    combined = combined[:10]  # cap global
    return combined, errors
