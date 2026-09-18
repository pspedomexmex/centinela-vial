"""
Monitor periódico de viajes activos.
Se ejecuta cada 30 min y manda alertas si hay incidentes nuevos.
"""
import asyncio
import hashlib
import logging
from telegram import Bot
from telegram.constants import ParseMode

from db.trips import get_viajes_activos, ya_enviada, marcar_enviada, limpiar_alertas_viejas
from sources.waze_incidents import get_incidents_for_regions
from sources.capufe_monitor import get_capufe_alerts_for_regions
from sources.twitter_monitor import get_tweets_for_regions
from sources.gmaps_traffic import get_traffic_status, EMOJI_TRAFICO
from regions.mexico_regions import REGIONS

logger = logging.getLogger(__name__)


def _hash_incidente(inc: dict) -> str:
    key = f"{inc.get('tipo','')}{inc.get('descripcion','')[:80]}"
    return hashlib.md5(key.encode()).hexdigest()


def _formato_incidente(inc: dict) -> str:
    linea = f"{inc['emoji']} *{inc['tipo']}*\n{inc['descripcion']}"
    if inc.get("autor"):
        linea += f"\n_Fuente: {inc['autor']}_"
    return linea


async def check_and_notify(bot: Bot, gmaps_key: str, twitter_token: str):
    """Revisar todos los viajes activos y enviar alertas nuevas."""
    limpiar_alertas_viejas(horas=6)
    viajes = get_viajes_activos()

    if not viajes:
        return

    for viaje in viajes:
        chat_id = viaje["chat_id"]
        regiones = viaje["regiones"]

        if not regiones:
            continue

        # Recolectar incidentes de todas las fuentes en paralelo
        waze_task = get_incidents_for_regions(regiones)
        capufe_task = get_capufe_alerts_for_regions(regiones, REGIONS)
        twitter_task = get_tweets_for_regions(regiones, REGIONS, twitter_token)

        waze_inc, capufe_inc, twitter_inc = await asyncio.gather(
            waze_task, capufe_task, twitter_task
        )

        todos = waze_inc + capufe_inc + twitter_inc

        # Filtrar ya enviados y críticos
        nuevos = []
        for inc in todos:
            h = _hash_incidente(inc)
            if not ya_enviada(chat_id, h):
                nuevos.append((inc, h))

        if not nuevos:
            continue

        # Armar mensaje
        lines = [f"🚨 *Alertas nuevas en tu ruta* — {viaje['origen']} → {viaje['destino']}\n"]
        for inc, h in nuevos[:8]:  # máximo 8 por ciclo
            lines.append(_formato_incidente(inc))
            lines.append("")

        mensaje = "\n".join(lines)

        try:
            await bot.send_message(
                chat_id=chat_id,
                text=mensaje,
                parse_mode=ParseMode.MARKDOWN,
            )
            for _, h in nuevos[:8]:
                marcar_enviada(chat_id, h)
        except Exception as e:
            logger.error(f"Error enviando a {chat_id}: {e}")


async def reporte_trafico_periodico(bot: Bot, gmaps_key: str):
    """Cada hora: resumen de tráfico actual para viajes activos."""
    viajes = get_viajes_activos()
    for viaje in viajes:
        chat_id = viaje["chat_id"]
        status = get_traffic_status(viaje["origen"], viaje["destino"], gmaps_key)
        if status.get("error"):
            continue

        nivel = status["nivel"]
        emoji = EMOJI_TRAFICO[nivel]
        demora = status["demora_min"]

        if nivel == "libre":
            texto = f"{emoji} *Tráfico libre* en tu ruta\n_{viaje['origen']} → {viaje['destino']}_"
        else:
            texto = (
                f"{emoji} *Tráfico {nivel}* en tu ruta\n"
                f"_{viaje['origen']} → {viaje['destino']}_\n"
                f"⏱ Demora aprox: *{demora} min* extra"
            )

        try:
            await bot.send_message(chat_id=chat_id, text=texto, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error enviando reporte tráfico a {chat_id}: {e}")
