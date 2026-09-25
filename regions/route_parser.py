"""
Calcula rutas y detecta regiones.
Con GMAPS_KEY: usa Google Maps Directions (distancia y tiempo reales).
Sin GMAPS_KEY: fallback local con diccionario ciudad→región + BFS de adyacencia.
"""
import unicodedata
from collections import deque

try:
    import googlemaps
    _GMAPS_AVAILABLE = True
except ImportError:
    _GMAPS_AVAILABLE = False


def _normalizar(texto: str) -> str:
    """'Querétaro' → 'queretaro': minúsculas + sin acentos ni diacríticos."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


# ------------------------------------------------------------------
# Fallback local — diccionario completo de ciudades/estados → región
# Todas las claves están sin acentos (el lookup normaliza la entrada).
# Cuando una ciudad existe en dos estados se conserva la más relevante
# para rutas de carga; las variantes con estado se incluyen explícitamente.
# ------------------------------------------------------------------

CIUDAD_A_REGION: dict[str, str] = {

    # ── ESTADOS (nombres completos y abreviaturas) ──────────────────
    "baja california":       "noroeste", "bc":              "noroeste",
    "baja california sur":   "noroeste", "bcs":             "noroeste",
    "sonora":                "noroeste", "son":             "noroeste",
    "sinaloa":               "noroeste", "sin":             "noroeste",
    "chihuahua estado":      "norte",    "coahuila":        "norte",
    "coah":                  "norte",    "durango estado":  "norte",
    "nuevo leon":            "noreste",  "nl":              "noreste",
    "tamaulipas":            "noreste",  "tam":             "noreste",
    "san luis potosi estado":"noreste",  "slp":             "noreste",
    "jalisco":               "occidente","jal":             "occidente",
    "nayarit":               "occidente","nay":             "occidente",
    "colima estado":         "occidente","col":             "occidente",
    "michoacan":             "occidente","mich":            "occidente",
    "queretaro estado":      "centro_norte","qro":          "centro_norte",
    "guanajuato estado":     "centro_norte","gto":          "centro_norte",
    "aguascalientes estado": "centro_norte","ags":          "centro_norte",
    "zacatecas estado":      "centro_norte","zac":          "centro_norte",
    "ciudad de mexico":      "centro",   "cdmx":            "centro",
    "df":                    "centro",   "estado de mexico":"centro",
    "edomex":                "centro",   "hidalgo":         "centro",
    "hgo":                   "centro",   "tlaxcala estado": "centro",
    "tlax":                  "centro",   "puebla estado":   "centro",
    "pue":                   "centro",   "morelos":         "centro",
    "mor":                   "centro",   "guerrero":        "centro",
    "gro":                   "centro",
    "veracruz estado":       "golfo",    "ver":             "golfo",
    "tabasco":               "golfo",    "tab":             "golfo",
    "oaxaca estado":         "golfo",    "oax":             "golfo",
    "chiapas":               "golfo",    "chis":            "golfo",
    "campeche estado":       "peninsula","camp":            "peninsula",
    "yucatan":               "peninsula","yuc":             "peninsula",
    "quintana roo":          "peninsula","qroo":            "peninsula",

    # ── NOROESTE — Baja California ──────────────────────────────────
    "tijuana":           "noroeste", "tecate":            "noroeste",
    "mexicali":          "noroeste", "rosarito":          "noroeste",
    "ensenada":          "noroeste", "san quintin":       "noroeste",
    "san felipe":        "noroeste",

    # ── NOROESTE — Baja California Sur ──────────────────────────────
    "la paz":            "noroeste", "los cabos":         "noroeste",
    "cabo san lucas":    "noroeste", "san jose del cabo": "noroeste",
    "loreto bcs":        "noroeste", "santa rosalia":     "noroeste",
    "guerrero negro":    "noroeste", "ciudad constitucion":"noroeste",

    # ── NOROESTE — Sonora ───────────────────────────────────────────
    "hermosillo":        "noroeste", "nogales":           "noroeste",
    "cd obregon":        "noroeste", "ciudad obregon":    "noroeste",
    "obregon":           "noroeste", "guaymas":           "noroeste",
    "empalme":           "noroeste", "navojoa":           "noroeste",
    "agua prieta":       "noroeste", "santa ana son":     "noroeste",
    "caborca":           "noroeste", "magdalena son":     "noroeste",
    "alamos":            "noroeste", "puerto penasco":    "noroeste",
    "san luis rio colorado":"noroeste",

    # ── NOROESTE — Sinaloa ──────────────────────────────────────────
    "culiacan":          "noroeste", "mazatlan":          "noroeste",
    "los mochis":        "noroeste", "guasave":           "noroeste",
    "ahome":             "noroeste", "guamuchil":         "noroeste",
    "mocorito":          "noroeste", "rosario sin":       "noroeste",
    "escuinapa":         "noroeste", "el fuerte":         "noroeste",

    # ── NORTE — Chihuahua ───────────────────────────────────────────
    "chihuahua":         "norte",    "juarez":            "norte",
    "ciudad juarez":     "norte",    "cd juarez":         "norte",
    "delicias":          "norte",    "cuauhtemoc chih":   "norte",
    "parral":            "norte",    "hidalgo del parral":"norte",
    "nuevo casas grandes":"norte",   "ojinaga":           "norte",
    "camargo chih":      "norte",    "jimenez":           "norte",

    # ── NORTE — Durango ─────────────────────────────────────────────
    "durango":           "norte",    "gomez palacio":     "norte",
    "lerdo":             "norte",    "santiago papasquiaro":"norte",
    "vicente guerrero dgo":"norte",  "canatlán":          "norte",

    # ── NORTE — Coahuila ────────────────────────────────────────────
    "saltillo":          "norte",    "torreon":           "norte",
    "monclova":          "norte",    "piedras negras":    "norte",
    "acuna":             "norte",    "ciudad acuna":      "norte",
    "cd acuna":          "norte",    "sabinas coah":      "norte",
    "nueva rosita":      "norte",    "muzquiz":           "norte",
    "frontera coah":     "norte",    "ramos arizpe":      "norte",
    "parras":            "norte",    "allende coah":      "norte",

    # ── NORESTE — Nuevo León ────────────────────────────────────────
    "monterrey":         "noreste",  "san nicolas":       "noreste",
    "apodaca":           "noreste",  "escobedo":          "noreste",
    "general escobedo":  "noreste",  "santa catarina nl": "noreste",
    "garcia nl":         "noreste",  "linares":           "noreste",
    "montemorelos":      "noreste",  "cadereyta nl":      "noreste",
    "sabinas hidalgo":   "noreste",  "cerralvo":          "noreste",
    "guadalupe nl":      "noreste",  "san pedro garza garcia":"noreste",
    "santiago nl":       "noreste",

    # ── NORESTE — Tamaulipas ────────────────────────────────────────
    "nuevo laredo":      "noreste",  "laredo":            "noreste",
    "reynosa":           "noreste",  "matamoros":         "noreste",
    "tampico":           "noreste",  "altamira":          "noreste",
    "ciudad madero":     "noreste",  "cd madero":         "noreste",
    "victoria":          "noreste",  "cd victoria":       "noreste",
    "ciudad victoria":   "noreste",  "mante":             "noreste",
    "ciudad mante":      "noreste",  "cd mante":          "noreste",
    "valle hermoso":     "noreste",  "rio bravo":         "noreste",
    "miguel aleman":     "noreste",  "camargo tam":       "noreste",
    "gonzalez":          "noreste",  "el mante":          "noreste",

    # ── NORESTE — San Luis Potosí ───────────────────────────────────
    "san luis potosi":   "noreste",  "matehuala":         "noreste",
    "rioverde":          "noreste",  "ciudad valles":     "noreste",
    "cd valles":         "noreste",  "tamazunchale":      "noreste",
    "cerritos":          "noreste",  "venado":            "noreste",
    "ebano":             "noreste",  "soledad":           "noreste",

    # ── OCCIDENTE — Jalisco ─────────────────────────────────────────
    "guadalajara":       "occidente","zapopan":           "occidente",
    "tlaquepaque":       "occidente","tonala jal":        "occidente",
    "tlajomulco":        "occidente","puerto vallarta":   "occidente",
    "lagos de moreno":   "occidente","ocotlan jal":       "occidente",
    "la barca":          "occidente","tepatitlan":        "occidente",
    "arandas":           "occidente","ciudad guzman":     "occidente",
    "cd guzman":         "occidente","autlan":            "occidente",
    "ameca":             "occidente","tequila":           "occidente",
    "encarnacion de diaz":"occidente","zapotlanejo":      "occidente",
    "acatlan de juarez": "occidente",

    # ── OCCIDENTE — Nayarit ─────────────────────────────────────────
    "tepic":             "occidente","bahia de banderas": "occidente",
    "nuevo vallarta":    "occidente","compostela":        "occidente",
    "san blas":          "occidente","ixtlan del rio":    "occidente",
    "tuxpan nay":        "occidente",

    # ── OCCIDENTE — Colima ──────────────────────────────────────────
    "colima":            "occidente","manzanillo":        "occidente",
    "tecoman":           "occidente","villa de alvarez":  "occidente",

    # ── OCCIDENTE — Michoacán ───────────────────────────────────────
    "morelia":           "occidente","uruapan":           "occidente",
    "zamora":            "occidente","lazaro cardenas":   "occidente",
    "apatzingan":        "occidente","la piedad":         "occidente",
    "jacona":            "occidente","patzcuaro":         "occidente",
    "sahuayo":           "occidente","zitacuaro":         "occidente",
    "maravatio":         "occidente","jiquilpan":         "occidente",
    "zacapu":            "occidente","los reyes mich":    "occidente",
    "hidalgo mich":      "occidente","puruaran":          "occidente",

    # ── CENTRO-NORTE / BAJÍO — Querétaro ────────────────────────────
    "queretaro":         "centro_norte","san juan del rio":"centro_norte",
    "tequisquiapan":     "centro_norte","cadereyta qro":  "centro_norte",
    "jalpan":            "centro_norte","amealco":        "centro_norte",
    "colon qro":         "centro_norte","pedro escobedo": "centro_norte",

    # ── CENTRO-NORTE / BAJÍO — Guanajuato ───────────────────────────
    "leon":              "centro_norte","irapuato":       "centro_norte",
    "celaya":            "centro_norte","salamanca":      "centro_norte",
    "silao":             "centro_norte","guanajuato":     "centro_norte",
    "san francisco del rincon":"centro_norte",
    "dolores hidalgo":   "centro_norte","acambaro":       "centro_norte",
    "salvatierra":       "centro_norte","cortazar":       "centro_norte",
    "uriangato":         "centro_norte","moroleon":       "centro_norte",
    "yuriria":           "centro_norte","abasolo gto":    "centro_norte",
    "valle de santiago": "centro_norte","san jose iturbide":"centro_norte",

    # ── CENTRO-NORTE / BAJÍO — Aguascalientes ───────────────────────
    "aguascalientes":    "centro_norte","rincon de romos":"centro_norte",
    "pabellon de arteaga":"centro_norte","calvillo":      "centro_norte",
    "jesus maria ags":   "centro_norte",

    # ── CENTRO-NORTE / BAJÍO — Zacatecas ────────────────────────────
    "zacatecas":         "centro_norte","fresnillo":      "centro_norte",
    "guadalupe zac":     "centro_norte","jerez":          "centro_norte",
    "jalpa":             "centro_norte","tlaltenango":    "centro_norte",
    "sombrerete":        "centro_norte","juan aldama zac":"centro_norte",
    "loreto zac":        "centro_norte","villanueva":     "centro_norte",
    "rio grande zac":    "centro_norte",

    # ── CENTRO — CDMX / Estado de México ────────────────────────────
    "mexico":            "centro",    "cdmx":             "centro",
    "df":                "centro",    "ciudad mexico":    "centro",
    "ecatepec":          "centro",    "naucalpan":        "centro",
    "tlalnepantla":      "centro",    "texcoco":          "centro",
    "nezahualcoyotl":    "centro",    "tultitlan":        "centro",
    "cuautitlan":        "centro",    "ixtapaluca":       "centro",
    "chalco":            "centro",    "metepec":          "centro",
    "toluca":            "centro",    "lerma":            "centro",
    "atlacomulco":       "centro",    "zumpango":         "centro",
    "tultepec":          "centro",    "tepotzotlan":      "centro",
    "huehuetoca":        "centro",    "coacalco":         "centro",

    # ── CENTRO — Hidalgo ────────────────────────────────────────────
    "pachuca":           "centro",    "tulancingo":       "centro",
    "tizayuca":          "centro",    "actopan":          "centro",
    "ixmiquilpan":       "centro",    "zimapan":          "centro",
    "huejutla":          "centro",    "tula":             "centro",
    "tepeji del rio":    "centro",    "tepeapulco":       "centro",
    "apan":              "centro",

    # ── CENTRO — Tlaxcala ───────────────────────────────────────────
    "tlaxcala":          "centro",    "apizaco":          "centro",
    "huamantla":         "centro",    "calpulalpan":      "centro",
    "san pablo del monte":"centro",   "zacatelco":        "centro",

    # ── CENTRO — Puebla ─────────────────────────────────────────────
    "puebla":            "centro",    "cholula":          "centro",
    "atlixco":           "centro",    "tehuacan":         "centro",
    "san martin texmelucan":"centro", "izucar de matamoros":"centro",
    "acatlan pue":       "centro",    "tepeaca":          "centro",
    "amozoc":            "centro",    "huejotzingo":      "centro",
    "cd serdan":         "centro",    "ciudad serdan":    "centro",
    "libres":            "centro",    "zacatlan":         "centro",

    # ── CENTRO — Morelos ────────────────────────────────────────────
    "cuernavaca":        "centro",    "cuautla":          "centro",
    "temixco":           "centro",    "jiutepec":         "centro",
    "yautepec":          "centro",    "jojutla":          "centro",
    "zacatepec":         "centro",    "puente de ixtla":  "centro",

    # ── CENTRO — Guerrero ───────────────────────────────────────────
    "chilpancingo":      "centro",    "acapulco":         "centro",
    "iguala":            "centro",    "taxco":            "centro",
    "zihuatanejo":       "centro",    "ixtapa":           "centro",
    "chilapa":           "centro",    "tlapa":            "centro",
    "cd altamirano":     "centro",    "ciudad altamirano":"centro",
    "petatlán":          "centro",    "tecpan":           "centro",

    # ── GOLFO — Veracruz ────────────────────────────────────────────
    "veracruz":          "golfo",     "xalapa":           "golfo",
    "coatzacoalcos":     "golfo",     "minatitlan":       "golfo",
    "orizaba":           "golfo",     "cordoba":          "golfo",
    "poza rica":         "golfo",     "tuxpan ver":       "golfo",
    "papantla":          "golfo",     "san andres tuxtla":"golfo",
    "cosamaloapan":      "golfo",     "acayucan":         "golfo",
    "cosoleacaque":      "golfo",     "coatepec":         "golfo",
    "perote":            "golfo",     "tierra blanca":    "golfo",
    "alvarado":          "golfo",     "boca del rio":     "golfo",
    "veracruz puerto":   "golfo",     "san juan bautista tuxtepec":"golfo",
    "tuxtepec":          "golfo",     "martinez de la torre":"golfo",

    # ── GOLFO — Tabasco ─────────────────────────────────────────────
    "villahermosa":      "golfo",     "cardenas tab":     "golfo",
    "comalcalco":        "golfo",     "huimanguillo":     "golfo",
    "paraiso":           "golfo",     "macuspana":        "golfo",
    "tenosique":         "golfo",     "jalpa de menendez":"golfo",

    # ── GOLFO — Oaxaca ──────────────────────────────────────────────
    "oaxaca":            "golfo",     "salina cruz":      "golfo",
    "huatulco":          "golfo",     "pochutla":         "golfo",
    "juchitan":          "golfo",     "tehuantepec":      "golfo",
    "miahuatlan":        "golfo",     "ocotlan oax":      "golfo",
    "tuxtepec oax":      "golfo",     "pinotepa nacional":"golfo",
    "cd ixtepec":        "golfo",     "matias romero":    "golfo",

    # ── GOLFO — Chiapas ─────────────────────────────────────────────
    "tuxtla":            "golfo",     "tuxtla gutierrez": "golfo",
    "tapachula":         "golfo",     "san cristobal":    "golfo",
    "san cristobal de las casas":"golfo","comitan":       "golfo",
    "palenque":          "golfo",     "tonala chis":      "golfo",
    "arriaga":           "golfo",     "ocozocoautla":     "golfo",
    "cintalapa":         "golfo",     "pichucalco":       "golfo",
    "villaflores":       "golfo",     "huixtla":          "golfo",
    "mapastepec":        "golfo",

    # ── PENÍNSULA DE YUCATÁN ────────────────────────────────────────
    "merida":            "peninsula", "cancun":           "peninsula",
    "campeche":          "peninsula", "chetumal":         "peninsula",
    "playa del carmen":  "peninsula", "cozumel":          "peninsula",
    "tulum":             "peninsula", "valladolid yuc":   "peninsula",
    "progreso":          "peninsula", "izamal":           "peninsula",
    "ticul":             "peninsula", "motul":            "peninsula",
    "felipe carrillo puerto":"peninsula","bacalar":       "peninsula",
    "ciudad del carmen": "peninsula", "cd del carmen":    "peninsula",
    "champoton":         "peninsula", "hopelchen":        "peninsula",
    "escarcega":         "peninsula", "jose maria morelos":"peninsula",
    "tekax":             "peninsula", "tizimin":          "peninsula",
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
    clave = _normalizar(nombre)
    if clave in CIUDAD_A_REGION:
        return CIUDAD_A_REGION[clave]
    # Búsqueda parcial: "San Luis" encuentra "san luis potosi", etc.
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
        "city_path": None,
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

def _via_city_graph(
    origen: str, destino: str,
    flow_overrides: dict | None = None,
) -> dict | None:
    """
    Intenta resolver la ruta via grafo de ciudades-hub.
    flow_overrides: {city_key: kmh} — si se pasa, Dijkstra usa tráfico real.
    """
    from regions.city_graph import (
        resolve_city, dijkstra_city_path, city_path_to_regions,
        CITY_LABELS, route_stats, route_stats_realtime, route_fuel,
    )
    ok = resolve_city(origen)
    dk = resolve_city(destino)
    if not ok or not dk:
        return None

    city_path = dijkstra_city_path(ok, dk, by_time=True, flow_overrides=flow_overrides)
    if not city_path:
        return None

    stats = route_stats_realtime(city_path, flow_overrides) if flow_overrides else route_stats(city_path)
    fuel  = route_fuel(city_path)
    regiones = city_path_to_regions(city_path)
    return {
        "error": None,
        "origen_fmt": CITY_LABELS.get(ok, origen.title()),
        "destino_fmt": CITY_LABELS.get(dk, destino.title()),
        "distancia_km": stats["km"],
        "duracion_hrs": stats["hrs"],
        "combustible":  fuel,
        "regiones": regiones,
        "city_path": city_path,
        "estados": [],
        "realtime": bool(flow_overrides),
    }


def calcular_ruta_y_regiones(
    origen: str, destino: str, gmaps_key: str,
    flow_overrides: dict | None = None,
) -> dict:
    # Prioridad 1: grafo de ciudades-hub (preciso, sin API externa)
    city_result = _via_city_graph(origen, destino, flow_overrides)
    if city_result:
        return city_result

    # Prioridad 2: Google Maps Directions (si hay key)
    if gmaps_key and _GMAPS_AVAILABLE:
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
                "city_path": None,
                "estados": [],
            }
        except Exception:
            pass

    # Prioridad 3: fallback regional (BFS de 8 regiones)
    return _fallback_local(origen, destino)
