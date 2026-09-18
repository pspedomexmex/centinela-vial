"""
Calcula rutas entre ciudades y determina qué regiones de México cruza.
Usa Google Maps Directions API.
"""
import re
import googlemaps
from .mexico_regions import ESTADO_A_REGION, REGIONS


# Mapeo de nombres de estados en Google Maps → clave interna
GMAPS_ESTADO_MAP = {
    "baja california": "noroeste",
    "baja california sur": "noroeste",
    "sonora": "noroeste",
    "sinaloa": "noroeste",
    "chihuahua": "norte",
    "durango": "norte",
    "coahuila": "norte",
    "coahuila de zaragoza": "norte",
    "nuevo león": "noreste",
    "nuevo leon": "noreste",
    "tamaulipas": "noreste",
    "san luis potosí": "noreste",
    "san luis potosi": "noreste",
    "jalisco": "occidente",
    "nayarit": "occidente",
    "colima": "occidente",
    "michoacán": "occidente",
    "michoacan": "occidente",
    "michoacán de ocampo": "occidente",
    "zacatecas": "centro_norte",
    "aguascalientes": "centro_norte",
    "guanajuato": "centro_norte",
    "querétaro": "centro_norte",
    "queretaro": "centro_norte",
    "ciudad de méxico": "centro",
    "ciudad de mexico": "centro",
    "estado de méxico": "centro",
    "estado de mexico": "centro",
    "hidalgo": "centro",
    "tlaxcala": "centro",
    "puebla": "centro",
    "morelos": "centro",
    "veracruz": "golfo",
    "veracruz de ignacio de la llave": "golfo",
    "tabasco": "golfo",
    "oaxaca": "golfo",
    "chiapas": "golfo",
    "campeche": "peninsula",
    "yucatán": "peninsula",
    "yucatan": "peninsula",
    "quintana roo": "peninsula",
}


def extraer_estado_de_componente(address_components: list) -> str | None:
    for c in address_components:
        if "administrative_area_level_1" in c.get("types", []):
            return c.get("long_name", "").lower()
    return None


def calcular_ruta_y_regiones(origen: str, destino: str, gmaps_key: str) -> dict:
    """
    Devuelve:
      - origen_fmt, destino_fmt: nombres formateados
      - distancia_km, duracion_hrs
      - regiones: lista ordenada de region keys que cruza la ruta
      - waypoints: lista de estados que cruza
      - polyline: encoded polyline para referencia
      - error: None o mensaje de error
    """
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
        origen_fmt = leg["start_address"]
        destino_fmt = leg["end_address"]
        distancia_m = leg["distance"]["value"]
        duracion_s = leg["duration"]["value"]

        # Geocodificar puntos intermedios para detectar estados
        polyline = directions[0]["overview_polyline"]["bounds"]
        steps = leg["steps"]

        estados_vistos = []
        regiones_ordenadas = []

        # Muestrear puntos a lo largo de la ruta
        points_to_check = []
        points_to_check.append(leg["start_location"])
        for step in steps[::max(1, len(steps) // 8)]:  # ~8 muestras
            points_to_check.append(step["end_location"])
        points_to_check.append(leg["end_location"])

        for point in points_to_check:
            try:
                geocode = client.reverse_geocode(
                    (point["lat"], point["lng"]),
                    language="es",
                    result_type="administrative_area_level_1",
                )
                if geocode:
                    estado = extraer_estado_de_componente(geocode[0]["address_components"])
                    if estado and estado not in estados_vistos:
                        estados_vistos.append(estado)
                        region = GMAPS_ESTADO_MAP.get(estado)
                        if region and region not in regiones_ordenadas:
                            regiones_ordenadas.append(region)
            except Exception:
                continue

        return {
            "error": None,
            "origen_fmt": origen_fmt,
            "destino_fmt": destino_fmt,
            "distancia_km": round(distancia_m / 1000),
            "duracion_hrs": round(duracion_s / 3600, 1),
            "regiones": regiones_ordenadas,
            "estados": estados_vistos,
            "polyline": directions[0]["overview_polyline"]["points"],
        }

    except Exception as e:
        return {"error": str(e)}
