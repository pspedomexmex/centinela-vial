"""
Consulta Google Maps para tráfico en tiempo real sobre la ruta activa.
"""
import googlemaps
from datetime import datetime


def get_traffic_status(origen: str, destino: str, gmaps_key: str) -> dict:
    """Compara duración normal vs con tráfico actual."""
    if not gmaps_key:
        return {"error": "no_key"}
    try:
        client = googlemaps.Client(key=gmaps_key)

        now = client.directions(
            origin=f"{origen}, México",
            destination=f"{destino}, México",
            mode="driving",
            departure_time=datetime.now(),
            traffic_model="best_guess",
            language="es",
            region="mx",
        )

        if not now:
            return {"error": "Sin datos de tráfico"}

        leg = now[0]["legs"][0]
        duracion_normal_s = leg["duration"]["value"]
        duracion_trafico_s = leg.get("duration_in_traffic", {}).get("value", duracion_normal_s)

        demora_min = round((duracion_trafico_s - duracion_normal_s) / 60)
        nivel = _nivel_trafico(demora_min)

        return {
            "error": None,
            "duracion_normal_min": round(duracion_normal_s / 60),
            "duracion_trafico_min": round(duracion_trafico_s / 60),
            "demora_min": demora_min,
            "nivel": nivel,
            "distancia_km": round(leg["distance"]["value"] / 1000),
        }
    except Exception as e:
        return {"error": str(e)}


def _nivel_trafico(demora_min: int) -> str:
    if demora_min <= 5:
        return "libre"
    elif demora_min <= 20:
        return "moderado"
    elif demora_min <= 45:
        return "lento"
    else:
        return "congestionado"


EMOJI_TRAFICO = {
    "libre": "🟢",
    "moderado": "🟡",
    "lento": "🟠",
    "congestionado": "🔴",
}
