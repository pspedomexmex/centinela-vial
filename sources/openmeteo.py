"""
OpenMeteo — clima severo en ciudades del path de la ruta.
API gratuita, sin clave. https://open-meteo.com/
Consulta condiciones actuales en cada ciudad intermedia y alerta
sobre niebla, tormentas, lluvia intensa, granizo y viento fuerte.
"""
import httpx
import asyncio

OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"

# WMO Weather Interpretation Codes → (emoji, descripción, es_severo)
_WMO: dict[int, tuple[str, str, bool]] = {
    0:  ("☀️",  "Despejado",                      False),
    1:  ("🌤",  "Mayormente despejado",            False),
    2:  ("⛅",  "Parcialmente nublado",            False),
    3:  ("☁️",  "Nublado",                         False),
    45: ("🌫️",  "Niebla",                          True),
    48: ("🌫️",  "Niebla con escarcha",             True),
    51: ("🌦",  "Llovizna ligera",                 False),
    53: ("🌦",  "Llovizna moderada",               False),
    55: ("🌧",  "Llovizna intensa",                True),
    56: ("🌧",  "Llovizna engelante",              True),
    57: ("🌧",  "Llovizna engelante intensa",      True),
    61: ("🌧",  "Lluvia ligera",                   False),
    63: ("🌧",  "Lluvia moderada",                 False),
    65: ("🌧",  "Lluvia intensa",                  True),
    71: ("❄️",  "Nevada ligera",                   True),
    73: ("❄️",  "Nevada moderada",                 True),
    75: ("❄️",  "Nevada intensa",                  True),
    77: ("🌨",  "Granizo",                         True),
    80: ("🌦",  "Chubascos ligeros",               False),
    81: ("🌧",  "Chubascos moderados",             False),
    82: ("⛈",  "Chubascos intensos",              True),
    85: ("❄️",  "Chubascos de nieve",              True),
    86: ("❄️",  "Chubascos de nieve intensos",     True),
    95: ("⛈",  "Tormenta eléctrica",              True),
    96: ("⛈",  "Tormenta con granizo",            True),
    99: ("⛈",  "Tormenta con granizo intenso",    True),
}

_VIENTO_FUERTE  = 70   # km/h
_VISIB_MUY_BAJA = 500  # metros
_VISIB_BAJA     = 1500 # metros


async def _fetch_weather(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    try:
        r = await client.get(
            OPENMETEO_URL,
            params={
                "latitude":     lat,
                "longitude":    lon,
                "current":      "temperature_2m,precipitation,weather_code,"
                                "wind_speed_10m,visibility",
                "timezone":     "America/Mexico_City",
                "wind_speed_unit": "kmh",
            },
            timeout=12,
        )
        r.raise_for_status()
        return r.json().get("current", {})
    except Exception:
        return {}


async def get_weather_alerts_for_city_route(city_path: list[str]) -> list[dict]:
    """
    Retorna alertas de clima severo en las ciudades intermedias del path.
    Solo reporta condiciones que afecten la conducción (niebla, tormenta,
    granizo, nevada, viento fuerte, visibilidad reducida).
    """
    if not city_path:
        return []

    from regions.city_graph import get_route_segments, CITY_LABELS

    segments = get_route_segments(city_path)
    if not segments:
        return []

    points = [(city, lat, lon) for city, lat, lon, _ in segments]

    async with httpx.AsyncClient(timeout=15) as client:
        results = await asyncio.gather(
            *[_fetch_weather(client, lat, lon) for _, lat, lon in points]
        )

    alertas: list[dict] = []
    for (city, _, _), wx in zip(points, results):
        if not wx:
            continue

        code    = wx.get("weather_code", 0)
        wind    = wx.get("wind_speed_10m", 0) or 0
        visib   = wx.get("visibility", 99999) or 99999
        precip  = wx.get("precipitation", 0) or 0

        emoji_w, desc_w, is_severe = _WMO.get(code, ("🌤", "Normal", False))
        label = CITY_LABELS.get(city, city)

        partes: list[str] = []

        if is_severe:
            partes.append(f"{emoji_w} {desc_w}")
        if wind >= _VIENTO_FUERTE:
            partes.append(f"💨 Viento {int(wind)} km/h")
        if visib <= _VISIB_MUY_BAJA:
            partes.append(f"🌫️ Visibilidad {int(visib)} m")
        elif visib <= _VISIB_BAJA and not is_severe:
            partes.append(f"🌫️ Visibilidad reducida {int(visib)} m")

        if not partes:
            continue

        # Severidad: tormentas=9, nevada/granizo=8, niebla=7, lluvia intensa=6, viento=5
        sev_map = {95: 9, 96: 9, 99: 9, 75: 8, 77: 8, 85: 8, 86: 8,
                   45: 7, 48: 7, 65: 6, 82: 6, 71: 7, 73: 7}
        sev = sev_map.get(code, 5 if wind >= _VIENTO_FUERTE else 4)

        alertas.append({
            "tipo":        "Condición climática",
            "emoji":       emoji_w,
            "descripcion": f"Cerca de {label}: {', '.join(partes)}",
            "severidad":   sev,
            "fuente":      "OpenMeteo",
            "hora":        None,
        })

    alertas.sort(key=lambda x: x["severidad"], reverse=True)
    return alertas


async def get_weather_alerts_for_regions(region_keys: list[str]) -> list[dict]:
    """Fallback cuando no hay city_path: usa tile ancla de cada región."""
    if not region_keys:
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

    async with httpx.AsyncClient(timeout=15) as client:
        results = await asyncio.gather(
            *[_fetch_weather(client, lat, lon) for _, lat, lon in points]
        )

    alertas: list[dict] = []
    for (key, _, _), wx in zip(points, results):
        if not wx:
            continue
        code  = wx.get("weather_code", 0)
        wind  = wx.get("wind_speed_10m", 0) or 0
        visib = wx.get("visibility", 99999) or 99999

        emoji_w, desc_w, is_severe = _WMO.get(code, ("🌤", "Normal", False))
        nombre = REGIONS.get(key, {}).get("nombre", key)

        partes: list[str] = []
        if is_severe:
            partes.append(f"{emoji_w} {desc_w}")
        if wind >= _VIENTO_FUERTE:
            partes.append(f"💨 Viento {int(wind)} km/h")
        if visib <= _VISIB_BAJA:
            partes.append(f"🌫️ Visibilidad {int(visib)} m")
        if not partes:
            continue

        sev_map = {95: 9, 96: 9, 99: 9, 75: 8, 77: 8, 45: 7, 48: 7, 65: 6}
        sev = sev_map.get(code, 5)
        alertas.append({
            "tipo":        "Condición climática",
            "emoji":       emoji_w,
            "descripcion": f"Región {nombre}: {', '.join(partes)}",
            "severidad":   sev,
            "fuente":      "OpenMeteo",
            "hora":        None,
        })

    alertas.sort(key=lambda x: x["severidad"], reverse=True)
    return alertas
