"""
Agente IA para consultas en lenguaje natural sobre la ruta activa.
Usa Groq API (free tier) con Llama 3.3 70B y tool calling.
"""
import os
import json
import asyncio
from groq import AsyncGroq

from db.supabase_client import get_viaje
from regions.route_parser import calcular_ruta_y_regiones
from sources.tomtom_incidents import (
    get_incidents_for_city_route,
    get_incidents_for_regions,
)
from sources.tomtom_flow import (
    get_flow_alerts_for_city_route,
    get_flow_alerts_for_regions,
)
from sources.openmeteo import (
    get_weather_alerts_for_city_route,
    get_weather_alerts_for_regions,
)
from sources.nitter_monitor import (
    get_tweets_for_city_route,
    get_tweets_for_regions,
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# Modelos con tool calling, en orden de preferencia
_PREFERRED_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.3-70b-specdec",
    "llama3-70b-8192",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
    "mixtral-8x7b-32768",
]


async def _select_model(client: AsyncGroq) -> str:
    """Elige el mejor modelo disponible en la cuenta Groq."""
    try:
        resp = await client.models.list()
        available = {m.id for m in resp.data}
        for m in _PREFERRED_MODELS:
            if m in available:
                return m
    except Exception:
        pass
    return _PREFERRED_MODELS[0]

_SYSTEM = (
    "Eres Centinela Vial, asistente de logística para transporte de carga en México. "
    "Respondes en español, de forma concisa y práctica. "
    "Combina los datos de las herramientas en una respuesta integrada — no listes datos crudos. "
    "Si hay incidentes graves, priorízalos y sugiere acción concreta al operador."
)

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_alertas_ruta",
            "description": "Incidentes TomTom (accidentes, cierres) y flujo vial en la ruta activa.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_clima_ruta",
            "description": "Condiciones climáticas severas a lo largo de la ruta activa.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_noticias_ruta",
            "description": "Noticias viales recientes y avisos oficiales (CAPUFE, SICT, Guardia Nacional).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calcular_ruta",
            "description": "Calcula ruta óptima entre dos ciudades: distancia, tiempo y ciudades intermedias.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origen":  {"type": "string", "description": "Ciudad de origen, ej: CDMX, Monterrey"},
                    "destino": {"type": "string", "description": "Ciudad de destino, ej: Guadalajara"},
                },
                "required": ["origen", "destino"],
            },
        },
    },
]


async def _exec_tool(name: str, args: dict, viaje: dict | None) -> str:
    city_path = viaje.get("city_path") if viaje else None
    regiones  = viaje.get("regiones", []) if viaje else []

    if name == "get_alertas_ruta":
        if not viaje:
            return "Sin viaje activo."
        if city_path:
            (incs, _), flows = await asyncio.gather(
                get_incidents_for_city_route(city_path),
                get_flow_alerts_for_city_route(city_path),
            )
        else:
            (incs, _), flows = await asyncio.gather(
                get_incidents_for_regions(regiones),
                get_flow_alerts_for_regions(regiones),
            )
        parts = []
        if incs:
            parts.append("Incidentes: " + "; ".join(i["descripcion"] for i in incs[:5]))
        else:
            parts.append("Sin incidentes críticos en la ruta.")
        if flows:
            parts.append("Flujo lento: " + "; ".join(f["descripcion"] for f in flows[:4]))
        else:
            parts.append("Flujo vial normal.")
        return "\n".join(parts)

    elif name == "get_clima_ruta":
        if not viaje:
            return "Sin viaje activo."
        if city_path:
            alerts = await get_weather_alerts_for_city_route(city_path)
        else:
            alerts = await get_weather_alerts_for_regions(regiones)
        if not alerts:
            return "Clima favorable en toda la ruta."
        return "Clima: " + "; ".join(a["descripcion"] for a in alerts[:4])

    elif name == "get_noticias_ruta":
        if not viaje:
            return "Sin viaje activo."
        if city_path:
            tweets, _ = await get_tweets_for_city_route(city_path)
        else:
            tweets, _ = await get_tweets_for_regions(regiones)
        if not tweets:
            return "Sin noticias viales recientes."
        return "Noticias: " + "; ".join(t["descripcion"] for t in tweets[:4])

    elif name == "calcular_ruta":
        origen  = args.get("origen", "")
        destino = args.get("destino", "")
        if not origen or not destino:
            return "Faltan origen o destino."
        resultado = calcular_ruta_y_regiones(origen, destino, "")
        if resultado.get("error"):
            return f"Error: {resultado['error']}"
        from regions.city_graph import CITY_LABELS
        path = resultado.get("city_path") or []
        via  = " → ".join(CITY_LABELS.get(c, c.title()) for c in path) if path else "N/D"
        return (
            f"Ruta: {via}\n"
            f"Distancia: {resultado.get('distancia_km')} km · "
            f"Tiempo: {resultado.get('duracion_hrs')} hrs"
        )

    return f"Herramienta '{name}' no reconocida."


async def run_agent(chat_id: int, user_message: str) -> str:
    if not GROQ_API_KEY:
        return "⚙️ GROQ_API_KEY no configurada. Agrégala en las variables de entorno."

    viaje = get_viaje(chat_id)

    ctx = ""
    if viaje:
        ctx = (
            f" Viaje activo: {viaje['origen']} → {viaje['destino']}, "
            f"{viaje.get('distancia_km')} km, {viaje.get('duracion_hrs')} hrs."
        )

    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM + ctx},
        {"role": "user",   "content": user_message},
    ]

    client = AsyncGroq(api_key=GROQ_API_KEY)
    model  = await _select_model(client)

    for _ in range(3):
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=_TOOLS,
            tool_choice="auto",
            max_tokens=800,
        )

        msg = response.choices[0].message

        if not msg.tool_calls:
            return msg.content or "Sin respuesta."

        # Agregar turno del asistente con sus tool_calls
        messages.append({
            "role":       "assistant",
            "content":    msg.content or "",
            "tool_calls": [
                {
                    "id":       tc.id,
                    "type":     "function",
                    "function": {
                        "name":      tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        # Ejecutar todas las herramientas en paralelo
        tool_results = await asyncio.gather(*[
            _exec_tool(
                tc.function.name,
                json.loads(tc.function.arguments or "{}"),
                viaje,
            )
            for tc in msg.tool_calls
        ])

        for tc, result in zip(msg.tool_calls, tool_results):
            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      result,
            })

    # Forzar respuesta final sin herramientas tras 3 rondas
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=800,
    )
    return response.choices[0].message.content or "Sin respuesta."
