"""
Escaneo en tiempo real de carreteras principales de la Zona Metropolitana
Valle de México — municipios norte: Ecatepec, Coacalco, Tecámac,
Tlalnepantla, Tultitlán y Cuautitlán Izcalli.

Usa TomTom Flow (velocidad actual) + Incidents (accidentes/cierres).
Comando: /zona
"""
import os
import asyncio
import math
import httpx

TOMTOM_KEY = os.environ.get("TOMTOM_KEY", "")
FLOW_URL    = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
_CONF_MIN   = 0.4   # umbral de confianza más bajo que el escaneo nacional (zona urbana)
_FF_MIN     = 20    # freeflow mínimo — filtra puntos en calle de barrio

# Categorías de incidentes relevantes para carga pesada
_CATS = {1, 3, 7, 8, 9, 11}  # Accidente, Peligroso, Carril cerrado, Cierre, Obras, Inundación

# (municipio, nombre_display, lat, lon, hw_code, require_federal, max_dist_km)
# require_federal=True  → solo incidentes con número MEX-XX exacto del tramo
# require_federal=False → cualquier incidente en el radio (vialidades urbanas sin num. MEX)
# max_dist_km           → radio máximo; autopistas = 10 km, vialidades urbanas = 5 km
TRAMOS_ZMVM: list[tuple[str, str, float, float, str, bool, int]] = [
    # ── MEX-85D (Autopista México–Pachuca, cuota) ──────────────────────────────────
    ("Ecatepec",           "MEX-85D — Ecatepec",              19.608, -99.015, "MEX-85D",  True,  10),
    ("Tecámac",            "MEX-85D — Tecámac",               19.700, -98.975, "MEX-85D",  True,  10),
    # ── MEX-85 libre (Carretera México–Pachuca, libre) ─────────────────────────────
    ("Ecatepec",           "MEX-85 libre — Ecatepec",         19.610, -99.008, "MEX-85",   True,  10),
    # ── MEX-132D (Autopista Ecatepec–Pirámides) ────────────────────────────────────
    ("Ecatepec",           "MEX-132D — Eje Pirámides",        19.597, -98.983, "MEX-132D", True,  10),
    # ── MEX-132 libre (Lechería–Texcoco) ──────────────────────────────────────────
    ("Coacalco",           "MEX-132 — Lechería/Texcoco",      19.630, -99.078, "MEX-132",  True,  10),
    # ── MEX-57D (Autopista México–Querétaro) ───────────────────────────────────────
    ("Tlalnepantla",       "MEX-57D — Tlalnepantla",          19.527, -99.213, "MEX-57D",  True,  10),
    ("Tultitlán",          "MEX-57D — Tultitlán",             19.650, -99.162, "MEX-57D",  True,  10),
    ("Cuautitlán Izcalli", "MEX-57D — Cuautitlán Izcalli",    19.658, -99.222, "MEX-57D",  True,  10),
    # ── Circuito Exterior Mexiquense (concesionada, sin num. MEX) ─────────────────
    ("Ecatepec",           "Circ. Ext. — Ecatepec",           19.635, -99.048, "ARCO",     False,  8),
    ("Coacalco",           "Circ. Ext. — Coacalco",           19.640, -99.088, "ARCO",     False,  8),
    ("Tultitlán",          "Circ. Ext. — Tultitlán",          19.656, -99.148, "ARCO",     False,  8),
    # ── Vialidades urbanas de Ecatepec ────────────────────────────────────────────
    ("Ecatepec",           "Vía Morelos",                     19.597, -99.038, "VIA",      False,  5),
    ("Ecatepec",           "Avenida Central",                 19.596, -99.052, "AV",       False,  5),
    ("Ecatepec",           "López Portillo",                  19.593, -98.995, "LP",       False,  5),
]

# Municipios en el orden en que aparecerán en el reporte
MUNICIPIOS_ORDEN = [
    "Ecatepec", "Coacalco", "Tecámac",
    "Tlalnepantla", "Tultitlán", "Cuautitlán Izcalli",
]


async def _flow_punto(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
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


def _dist_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = (lat2 - lat1) * 111.0
    dlon = (lon2 - lon1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat ** 2 + dlon ** 2)


async def _incidents_punto(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    hw: str,
    require_federal: bool,
    max_dist_km: int,
    label: str = "",       # nombre legible para la descripción (reemplaza hw en vialidades)
) -> list[dict]:
    from sources.tomtom_incidents import _fetch_tile, CATEGORIA, _extract_coords
    incs = await _fetch_tile(client, lat, lon)
    resultados = []
    for inc in incs:
        p   = inc.get("properties", {})
        cat = p.get("iconCategory", 0)
        if cat not in _CATS:
            continue

        if require_federal:
            roads = p.get("roadNumbers") or []
            if hw not in roads:
                continue

        # Descartar si está fuera del radio del tramo
        coords_inc = _extract_coords(inc)
        if coords_inc:
            inc_lat, inc_lon = coords_inc
            if _dist_km(lat, lon, inc_lat, inc_lon) > max_dist_km:
                continue
        else:
            inc_lat = inc_lon = None

        emoji, tipo = CATEGORIA.get(cat, ("⚠️", "Incidente"))
        mag     = p.get("magnitudeOfDelay", 0) or 0
        mag_txt = {1: "menor", 2: "moderado", 3: "grave", 4: "crítico"}.get(mag, "")
        desc    = f"{emoji} {tipo} en {label or hw}"
        if mag_txt:
            desc += f" ({mag_txt})"

        # Sentido del incidente — recortar antes del paréntesis para no repetir nombre de carretera
        def _cortar(s: str) -> str:
            return s.split("(")[0].strip(" ,/")

        desde = _cortar(p.get("from") or "")
        hasta = _cortar(p.get("to")   or "")
        if desde and hasta:
            direccion = f"↗ {desde} → {hasta}"
        elif desde:
            direccion = f"↗ desde {desde}"
        elif hasta:
            direccion = f"↗ hacia {hasta}"
        else:
            direccion = None

        resultados.append({
            "desc":      desc,
            "direccion": direccion,
            "lat":       inc_lat,
            "lon":       inc_lon,
        })
    return resultados[:2]


async def escaneo_zmvm_norte() -> dict[str, list[dict]]:
    """
    Escanea todos los tramos de la ZMVM Norte en paralelo.
    Retorna dict {municipio: [tramo_dict, ...]} ordenado por severidad.
    """
    if not TOMTOM_KEY:
        return {}

    async with httpx.AsyncClient(timeout=12) as client:
        flow_tasks = [
            _flow_punto(client, lat, lon)
            for _, _, lat, lon, _, _, _ in TRAMOS_ZMVM
        ]
        inc_tasks = [
            _incidents_punto(client, lat, lon, hw, req_fed, max_dist,
                             label=(nombre if not req_fed else ""))
            for _, nombre, lat, lon, hw, req_fed, max_dist in TRAMOS_ZMVM
        ]
        flow_res, inc_res = await asyncio.gather(
            asyncio.gather(*flow_tasks),
            asyncio.gather(*inc_tasks),
        )

    por_mun: dict[str, list[dict]] = {m: [] for m in MUNICIPIOS_ORDEN}

    for (mun, nombre, _, _, hw, _, _), flow, incidentes in zip(TRAMOS_ZMVM, flow_res, inc_res):
        current  = float(flow.get("currentSpeed",  0) or 0)
        freeflow = float(flow.get("freeFlowSpeed", 0) or 0)
        conf     = float(flow.get("confidence",    0) or 0)

        if freeflow >= _FF_MIN and conf >= _CONF_MIN:
            ratio = current / freeflow
        else:
            ratio = None

        if ratio is None:
            nivel, sev = "sin_datos", 0
        elif ratio < 0.40:
            nivel, sev = "MUY_LENTO", 3
        elif ratio < 0.65:
            nivel, sev = "LENTO", 2
        elif ratio < 0.85:
            nivel, sev = "MODERADO", 1
        else:
            nivel, sev = "NORMAL", 0

        if incidentes and any(hw in inc.get("desc", "") for inc in incidentes):
            sev = max(sev, 2)

        por_mun[mun].append({
            "nombre":     nombre,
            "hw":         hw,
            "velocidad":  round(current)  if current  else None,
            "libre":      round(freeflow) if freeflow else None,
            "ratio":      ratio,
            "nivel":      nivel,
            "incidentes": incidentes,
            "sev":        sev,
        })

    for mun in por_mun:
        por_mun[mun].sort(key=lambda x: -x["sev"])

    return por_mun
