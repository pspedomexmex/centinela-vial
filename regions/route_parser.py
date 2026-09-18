"""
Calcula rutas y detecta regiones usando bounding boxes — una sola llamada a Google Maps.
"""
import googlemaps

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


def calcular_ruta_y_regiones(origen: str, destino: str, gmaps_key: str) -> dict:
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

        # Muestrear puntos de la ruta para detectar regiones (sin API extra)
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

    except Exception as e:
        return {"error": str(e)}
