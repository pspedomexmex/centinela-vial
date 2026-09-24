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
)
from sources.tomtom_incidents import get_incidents_for_regions as _tomtom_incidents
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
    chat_id = viaje["chat_id"]
    regiones = viaje["regiones"]

    if not regiones:
        return

    (tomtom_inc, _), capufe_inc = await asyncio.gather(
        _tomtom_incidents(regiones),
        get_capufe_alerts_for_regions(regiones, REGIONS),
    )

    todos = tomtom_inc + capufe_inc
    nuevos = []

    for inc in todos:
        h = hash_incidente(inc)
        if not ya_enviada(chat_id, h):
            nuevos.append((inc, h))

    if not nuevos:
        logger.info(f"Sin incidentes nuevos para chat {chat_id}")
        return

    lines = [f"🚨 *Alertas en tu ruta* — {viaje['origen']} → {viaje['destino']}\n"]
    for inc, h in nuevos[:8]:
        lines.append(f"{inc['emoji']} *{inc['tipo']}*\n{inc['descripcion']}")
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
