"""
Calcula rutas y detecta regiones.
Con GMAPS_KEY: usa Google Maps Directions (distancia y tiempo reales).
Sin GMAPS_KEY: fallback local con diccionario ciudad→región + BFS de adyacencia.
"""
from collections import deque

try:
    import googlemaps
    _GMAPS_AVAILABLE = True
except ImportError:
    _GMAPS_AVAILABLE = False

# ------------------------------------------------------------------
# Fallback local
# ------------------------------------------------------------------

CIUDAD_A_REGION = {
    # Noroeste
    "tijuana": "noroeste", "mexicali": "noroeste", "ensenada": "noroeste",
    "hermosillo": "noroeste", "nogales": "noroeste", "obregon": "noroeste",
    "cd obregon": "noroeste", "guaymas": "noroeste",
    "culiacan": "noroeste", "mazatlan": "noroeste", "los mochis": "noroeste",
    # Norte
    "chihuahua": "norte", "juarez": "norte", "ciudad juarez": "norte",
    "cd juarez": "norte", "delicias": "norte", "parral": "norte",
    "torreon": "norte", "gomez palacio": "norte",
    "durango": "norte", "saltillo": "norte",
    # Noreste
    "monterrey": "noreste", "guadalupe": "noreste", "apodaca": "noreste",
    "nuevo laredo": "noreste", "laredo": "noreste",
    "reynosa": "noreste", "matamoros": "noreste", "tampico": "noreste",
    "victoria": "noreste", "cd victoria": "noreste", "ciudad victoria": "noreste",
    "san luis potosi": "noreste", "matehuala": "noreste", "rioverde": "noreste",
    # Occidente
    "guadalajara": "occidente", "zapopan": "occidente", "tlaquepaque": "occidente",
    "tepic": "occidente", "colima": "occidente", "manzanillo": "occidente",
    "morelia": "occidente", "uruapan": "occidente", "zamora": "occidente",
    "la piedad": "occidente", "lazaro cardenas": "occidente",
    # Centro-Norte / Bajío
    "queretaro": "centro_norte", "leon": "centro_norte", "irapuato": "centro_norte",
    "celaya": "centro_norte", "salamanca": "centro_norte", "silao": "centro_norte",
    "guanajuato": "centro_norte", "aguascalientes": "centro_norte",
    "zacatecas": "centro_norte", "fresnillo": "centro_norte",
    # Centro
    "cdmx": "centro", "ciudad de mexico": "centro", "mexico": "centro",
    "df": "centro", "ecatepec": "centro", "naucalpan": "centro",
    "toluca": "centro", "texcoco": "centro", "tlalnepantla": "centro",
    "puebla": "centro", "cholula": "centro", "atlixco": "centro",
    "cuernavaca": "centro", "cuautla": "centro",
    "pachuca": "centro", "tulancingo": "centro",
    "tlaxcala": "centro", "apizaco": "centro",
    # Golfo / Sureste
    "veracruz": "golfo", "xalapa": "golfo", "coatzacoalcos": "golfo",
    "minatitlan": "golfo", "orizaba": "golfo", "cordoba": "golfo",
    "villahermosa": "golfo", "cardenas": "golfo",
    "oaxaca": "golfo", "salina cruz": "golfo", "huatulco": "golfo",
    "tuxtla": "golfo", "tuxtla gutierrez": "golfo", "tapachula": "golfo",
    "san cristobal": "golfo", "comitan": "golfo",
    # Península de Yucatán
    "merida": "peninsula", "cancun": "peninsula", "campeche": "peninsula",
    "chetumal": "peninsula", "playa del carmen": "peninsula",
    "tulum": "peninsula", "valladolid": "peninsula", "progreso": "peninsula",
}

# Adyacencia entre regiones (grafo no dirigido)
ADYACENCIA = {
    "noroeste":    ["norte", "occidente"],
    "norte":       ["noroeste", "noreste", "centro_norte"],
    "noreste":     ["norte", "centro_norte", "golfo"],
    "occidente":   ["noroeste", "centro_norte", "centro"],
    "centro_norte":["norte", "noreste", "occidente", "centro"],
    "centro":      ["centro_norte", "golfo", "occidente"],
    "golfo":       ["noreste", "centro", "peninsula"],
    "peninsula":   ["golfo"],
}


def _region_para_ciudad(nombre: str) -> str | None:
    clave = nombre.lower().strip()
    if clave in CIUDAD_A_REGION:
        return CIUDAD_A_REGION[clave]
    for ciudad, region in CIUDAD_A_REGION.items():
        if ciudad in clave or clave in ciudad:
            return region
    return None


def _ruta_entre_regiones(origen: str, destino: str) -> list[str]:
    if origen == destino:
        return [origen]
    queue = deque([[origen]])
    visited = {origen}
    while queue:
        path = queue.popleft()
        for vecino in ADYACENCIA.get(path[-1], []):
            if vecino == destino:
                return path + [vecino]
            if vecino not in visited:
                visited.add(vecino)
                queue.append(path + [vecino])
    return [origen, destino]


def _fallback_local(origen: str, destino: str) -> dict:
    region_origen = _region_para_ciudad(origen)
    region_destino = _region_para_ciudad(destino)

    if not region_origen and not region_destino:
        return {"error": f"No se reconocen '{origen}' ni '{destino}'. Intenta con el nombre del estado o ciudad principal."}
    if not region_origen:
        return {"error": f"No se reconoce '{origen}'. Prueba con la ciudad o estado principal."}
    if not region_destino:
        return {"error": f"No se reconoce '{destino}'. Prueba con la ciudad o estado principal."}

    regiones = _ruta_entre_regiones(region_origen, region_destino)
    return {
        "error": None,
        "origen_fmt": origen.title(),
        "destino_fmt": destino.title(),
        "distancia_km": None,
        "duracion_hrs": None,
        "regiones": regiones,
        "estados": [],
    }


# ------------------------------------------------------------------
# Bounding boxes para el modo con GMAPS
# ------------------------------------------------------------------

REGION_BBOX = {
    "noroeste":     {"s": 22.5, "n": 32.7, "w": -117.1, "e": -108.0},
    "norte":        {"s": 24.0, "n": 31.8, "w": -108.0, "e": -98.5},
    "noreste":      {"s": 22.0, "n": 27.5, "w": -100.5, "e": -96.5},
    "occidente":    {"s": 18.5, "n": 23.5, "w": -105.5, "e": -99.5},
    "centro_norte": {"s": 20.5, "n": 24.5, "w": -103.0, "e": -98.5},
    "centro":       {"s": 18.5, "n": 20.5, "w": -100.5, "e": -97.5},
    "golfo":        {"s": 14.5, "n": 22.5, "w": -97.0,  "e": -90.5},
    "peninsula":    {"s": 17.5, "n": 21.5, "w": -90.5,  "e": -86.5},
}


def _region_para_punto(lat: float, lng: float) -> str | None:
    for region, b in REGION_BBOX.items():
        if b["s"] <= lat <= b["n"] and b["w"] <= lng <= b["e"]:
            return region
    return None


# ------------------------------------------------------------------
# Función principal
# ------------------------------------------------------------------

def calcular_ruta_y_regiones(origen: str, destino: str, gmaps_key: str) -> dict:
    if not gmaps_key or not _GMAPS_AVAILABLE:
        return _fallback_local(origen, destino)

    try:
        client = googlemaps.Client(key=gmaps_key)
        directions = client.directions(
            origin=f"{origen}, México",
            destination=f"{destino}, México",
            mode="driving",
            language="es",
            region="mx",
        )

        if not directions:
            return {"error": f"No se encontró ruta entre {origen} y {destino}"}

        leg = directions[0]["legs"][0]
        steps = leg["steps"]
        distancia_m = leg["distance"]["value"]
        duracion_s = leg["duration"]["value"]

        puntos = [leg["start_location"]]
        for step in steps[::max(1, len(steps) // 6)]:
            puntos.append(step["end_location"])
        puntos.append(leg["end_location"])

        regiones_ordenadas = []
        for p in puntos:
            r = _region_para_punto(p["lat"], p["lng"])
            if r and r not in regiones_ordenadas:
                regiones_ordenadas.append(r)

        return {
            "error": None,
            "origen_fmt": leg["start_address"],
            "destino_fmt": leg["end_address"],
            "distancia_km": round(distancia_m / 1000),
            "duracion_hrs": round(duracion_s / 3600, 1),
            "regiones": regiones_ordenadas,
            "estados": [],
        }

    except Exception:
        return _fallback_local(origen, destino)
