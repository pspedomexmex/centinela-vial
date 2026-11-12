"""
Escaneo en tiempo real de los principales tramos carreteros de México.
Combina TomTom Flow (velocidad actual) + Incidents (accidentes/cierres).
No requiere viaje activo — diagnóstico nacional bajo demanda.
"""
import os
import asyncio
import httpx

TOMTOM_KEY = os.environ.get("TOMTOM_KEY", "")
FLOW_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
_CONF_MINIMA = 0.5

# 27 tramos cortos clave para transporte de carga.
# Clave: (city_a, city_b, nombre_display)
# Midpoint y highway se calculan desde el grafo en tiempo de ejecución.
TRAMOS_CLAVE: list[tuple[str, str, str]] = [
    # ── Eje Norte MEX-57D/57 ────────────────────────────────────
    ("cdmx",            "queretaro",        "CDMX → Querétaro"),
    ("queretaro",       "san_luis_potosi",  "Querétaro → SLP"),
    ("san_luis_potosi", "matehuala",        "SLP → Matehuala"),
    ("matehuala",       "monterrey",        "Matehuala → Monterrey"),
    # ── Eje Golfo MEX-150D/180 ───────────────────────────────────
    ("cdmx",            "puebla",           "CDMX → Puebla"),
    ("puebla",          "veracruz",         "Puebla → Veracruz"),
    ("veracruz",        "coatzacoalcos",    "Veracruz → Coatzacoalcos"),
    ("coatzacoalcos",   "villahermosa",     "Coatzacoalcos → Villahermosa"),
    # ── Bajío / Occidente ────────────────────────────────────────
    ("queretaro",       "leon",             "Querétaro → León"),
    ("leon",            "guadalajara",      "León → Guadalajara"),
    ("guadalajara",     "tepic",            "Guadalajara → Tepic"),
    ("tepic",           "mazatlan",         "Tepic → Mazatlán"),
    ("mazatlan",        "culiacan",         "Mazatlán → Culiacán"),
    # ── Noreste ──────────────────────────────────────────────────
    ("monterrey",       "saltillo",         "Monterrey → Saltillo"),
    ("saltillo",        "torreon",          "Saltillo → Torreón"),
    ("monterrey",       "nuevo_laredo",     "Monterrey → Nuevo Laredo"),
    ("monterrey",       "reynosa",          "Monterrey → Reynosa"),
    # ── Norte ────────────────────────────────────────────────────
    ("durango",         "chihuahua",        "Durango → Chihuahua"),
    ("chihuahua",       "ciudad_juarez",    "Chihuahua → Cd. Juárez"),
    # ── Noroeste ─────────────────────────────────────────────────
    ("culiacan",        "hermosillo",       "Culiacán → Hermosillo"),
    ("hermosillo",      "nogales",          "Hermosillo → Nogales"),
    ("tijuana",         "mexicali",         "Tijuana → Mexicali"),
    # ── Sur ──────────────────────────────────────────────────────
    ("cdmx",            "cuernavaca",       "CDMX → Cuernavaca"),
    ("cuernavaca",      "acapulco",         "Cuernavaca → Acapulco"),
    # ── Sureste / Península ──────────────────────────────────────
    ("villahermosa",    "campeche",         "Villahermosa → Campeche"),
    ("campeche",        "merida",           "Campeche → Mérida"),
    # ── Oaxaca / Chiapas ─────────────────────────────────────────
    ("oaxaca",          "tuxtla",           "Oaxaca → Tuxtla"),
]


async def _flow_en_punto(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
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


async def _incidents_en_punto(
    client: httpx.AsyncClient, lat: float, lon: float, highway: str
) -> list[dict]:
    """
    Retorna lista de dicts con descripción y coordenadas del incidente.
    Solo incidentes en carreteras federales (MEX-XX).
    """
    from sources.tomtom_incidents import _fetch_tile, CATEGORIA
    # Categorías relevantes para escaneo nacional de carga pesada:
    # 1=Accidente, 3=Condiciones peligrosas, 7=Carril cerrado,
    # 8=Carretera cerrada, 9=Obras, 11=Inundación
    _CATS_ESCANEO = {1, 3, 7, 8, 9, 11}
    incs = await _fetch_tile(client, lat, lon)
    resultados = []
    for inc in incs:
        p   = inc.get("properties", {})
        cat = p.get("iconCategory", 0)
        if cat not in _CATS_ESCANEO:
            continue
        roads = p.get("roadNumbers") or []
        federal = [r for r in roads if "MEX-" in r or r.startswith("MEX")]
        if not federal:
            continue
        # Extraer coordenadas del punto medio de la geometría
        geom   = inc.get("geometry", {})
        coords = geom.get("coordinates", [])
        inc_lat, inc_lon = None, None
        if coords:
            mid = coords[len(coords) // 2]   # punto medio del LineString
            inc_lon, inc_lat = mid[0], mid[1] # GeoJSON: [lon, lat]

        emoji, tipo = CATEGORIA.get(cat, ("⚠️", "Incidente"))
        hw_label = federal[0] if federal else ""
        mag     = p.get("magnitudeOfDelay", 0) or 0
        mag_txt = {1: "menor", 2: "moderado", 3: "grave", 4: "crítico"}.get(mag, "")
        desc    = f"{emoji} {tipo} en {hw_label}"
        if mag_txt:
            desc += f" ({mag_txt})"
        resultados.append({"desc": desc, "lat": inc_lat, "lon": inc_lon})
    return resultados[:2]  # máx 2 incidentes por tramo


async def escaneo_nacional() -> list[dict]:
    """
    Escanea los 27 tramos clave en paralelo.
    Retorna lista de dicts ordenada de mayor a menor severidad.
    """
    if not TOMTOM_KEY:
        return []

    from regions.city_graph import CITY_NODES, CITY_EDGES

    # Construir puntos de consulta (midpoint de cada tramo)
    tramos_data = []
    for city_a, city_b, nombre in TRAMOS_CLAVE:
        coords_a = CITY_NODES.get(city_a)
        coords_b = CITY_NODES.get(city_b)
        if not coords_a or not coords_b:
            continue
        lat = (coords_a[0] + coords_b[0]) / 2
        lon = (coords_a[1] + coords_b[1]) / 2
        hw  = CITY_EDGES.get(city_a, {}).get(city_b, "")
        tramos_data.append({
            "nombre": nombre,
            "hw":     hw,
            "lat":    lat,
            "lon":    lon,
        })

    async with httpx.AsyncClient(timeout=12) as client:
        flow_tasks = [_flow_en_punto(client, t["lat"], t["lon"]) for t in tramos_data]
        inc_tasks  = [_incidents_en_punto(client, t["lat"], t["lon"], t["hw"]) for t in tramos_data]
        flow_results, inc_results = await asyncio.gather(
            asyncio.gather(*flow_tasks),
            asyncio.gather(*inc_tasks),
        )

    resultados = []
    for tramo, flow, incidentes in zip(tramos_data, flow_results, inc_results):
        current  = float(flow.get("currentSpeed",  0) or 0)
        freeflow = float(flow.get("freeFlowSpeed", 0) or 0)
        conf     = float(flow.get("confidence",    0) or 0)

        # Si freeflow < 30 km/h el punto cayó en calle urbana, no en autopista federal
        if freeflow >= 30 and conf >= _CONF_MINIMA:
            ratio = current / freeflow
        else:
            ratio = None

        # Nivel de flujo
        if ratio is None:
            nivel = "sin_datos"
            sev   = 0
        elif ratio < 0.40:
            nivel = "MUY_LENTO"
            sev   = 3
        elif ratio < 0.65:
            nivel = "LENTO"
            sev   = 2
        elif ratio < 0.85:
            nivel = "MODERADO"
            sev   = 1
        else:
            nivel = "NORMAL"
            sev   = 0

        # Solo los incidentes en la carretera exacta del tramo elevan severidad
        if incidentes and any(tramo["hw"] in inc.get("desc", "") for inc in incidentes):
            sev = max(sev, 2)

        resultados.append({
            "nombre":     tramo["nombre"],
            "hw":         tramo["hw"],
            "velocidad":  round(current) if current else None,
            "libre":      round(freeflow) if freeflow else None,
            "ratio":      ratio,
            "nivel":      nivel,
            "incidentes": incidentes,
            "sev":        sev,
        })

    # Ordenar: mayor severidad primero, luego alfabético
    resultados.sort(key=lambda x: (-x["sev"], x["nombre"]))
    return resultados
