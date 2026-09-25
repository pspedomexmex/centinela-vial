"""
Script de monitoreo periódico — ejecutado por GitHub Actions cada 30 min.
Revisa viajes activos en Supabase y envía alertas si hay incidentes nuevos.
"""
import os
import sys
import asyncio
import hashlib
import logging
import requests

# Agregar raíz del proyecto al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.supabase_client import (
    get_viajes_activos, ya_enviada, marcar_enviada, limpiar_alertas_viejas,
    actualizar_cierres,
)
from sources.tomtom_incidents import (
    get_incidents_for_city_route as _city_incidents,
    get_incidents_for_route as _region_incidents,
)
from sources.tomtom_flow import (
    get_flow_alerts_for_city_route as _city_flow,
    get_flow_alerts_for_regions as _region_flow,
)
from sources.openmeteo import (
    get_weather_alerts_for_city_route as _city_weather,
    get_weather_alerts_for_regions as _region_weather,
)
from sources.capufe_monitor import get_capufe_alerts_for_regions
from regions.mexico_regions import REGIONS

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_SEND = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def send_message(chat_id: int, text: str):
    try:
        requests.post(TELEGRAM_SEND, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }, timeout=10)
    except Exception as e:
        logger.error(f"Error enviando mensaje a {chat_id}: {e}")


def hash_incidente(inc: dict) -> str:
    return hashlib.md5(f"{inc['tipo']}{inc['descripcion'][:80]}".encode()).hexdigest()


async def check_viaje(viaje: dict):
    chat_id   = viaje["chat_id"]
    city_path = viaje.get("city_path")
    regiones  = viaje["regiones"]

    if not regiones:
        return

    # Lanzar las 3 fuentes en paralelo
    if city_path:
        inc_task     = _city_incidents(city_path)
        flow_task    = _city_flow(city_path)
        weather_task = _city_weather(city_path)
    else:
        inc_task     = _region_incidents(regiones)
        flow_task    = _region_flow(regiones)
        weather_task = _region_weather(regiones)

    (tomtom_inc, _), flow_inc, weather_inc = await asyncio.gather(
        inc_task, flow_task, weather_task,
    )

    # ── Detección de reaperturas ───────────────────────────────────
    cierres_actuales = {
        inc["cierre_hash"]: inc["descripcion"]
        for inc in tomtom_inc
        if inc.get("cierre_hash")
    }
    reabiertos = actualizar_cierres(chat_id, cierres_actuales)
    if reabiertos:
        lines_r = [f"✅ *Carretera reabierta* — {viaje['origen']} → {viaje['destino']}\n"]
        for desc in reabiertos:
            lines_r.append(f"✅ _{desc}_")
        send_message(chat_id, "\n".join(lines_r))
        logger.info(f"Reaperturas notificadas a chat {chat_id}: {len(reabiertos)}")

    # ── Alertas nuevas ─────────────────────────────────────────────
    todos  = tomtom_inc + flow_inc + weather_inc
    nuevos = []
    for inc in todos:
        h = hash_incidente(inc)
        if not ya_enviada(chat_id, h):
            nuevos.append((inc, h))

    if not nuevos:
        logger.info(f"Sin alertas nuevas para chat {chat_id}")
        return

    lines = [f"🚨 *Alertas* — {viaje['origen']} → {viaje['destino']}\n"]
    for inc, h in nuevos[:8]:
        hora = f" · _{inc['hora']} h_" if inc.get("hora") else ""
        lines.append(f"{inc['emoji']} *{inc['tipo']}*{hora}\n_{inc['descripcion']}_")
        if inc.get("coords"):
            lat, lon = inc["coords"]
            lines.append(f"📍 [Ver en mapa](https://maps.google.com/?q={lat},{lon})")
        if inc.get("autor"):
            lines.append(f"_— {inc['autor']}_")
        lines.append("")
        marcar_enviada(chat_id, h)

    send_message(chat_id, "\n".join(lines))
    logger.info(f"Alertas enviadas a chat {chat_id}: {len(nuevos)} nuevas")


async def main():
    logger.info("Centinela Vial Monitor iniciando...")
    limpiar_alertas_viejas(horas=6)

    viajes = get_viajes_activos()
    logger.info(f"Viajes activos: {len(viajes)}")

    if not viajes:
        return

    await asyncio.gather(*[check_viaje(v) for v in viajes])
    logger.info("Monitor completado.")


if __name__ == "__main__":
    asyncio.run(main())
