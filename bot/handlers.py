"""
Handlers del bot — compatibles con webhook (Bot directo, sin Application).
"""
import os
import asyncio
import logging
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from regions.route_parser import calcular_ruta_y_regiones
from regions.mexico_regions import REGIONS, get_regions_info
from sources.waze_incidents import get_incidents_for_regions
from sources.capufe_monitor import get_capufe_alerts_for_regions
from sources.gmaps_traffic import get_traffic_status, EMOJI_TRAFICO
from db.supabase_client import guardar_viaje, get_viaje, detener_viaje

logger = logging.getLogger(__name__)
GMAPS_KEY = os.environ.get("GMAPS_KEY", "")


async def cmd_start(bot: Bot, chat_id: int):
    await bot.send_message(
        chat_id=chat_id,
        parse_mode=ParseMode.MARKDOWN,
        text=(
            "🚛 *Centinela Vial* — Monitor de rutas para transporte de carga\n\n"
            "• `/viaje ORIGEN - DESTINO` — Iniciar monitoreo\n"
            "  Ej: `/viaje CDMX - Monterrey`\n\n"
            "• `/alertas` — Incidentes en tu ruta ahora\n"
            "• `/trafico` — Estado del tráfico\n"
            "• `/estado` — Resumen del viaje activo\n"
            "• `/regiones` — Regiones que cubre tu ruta\n"
            "• `/detener` — Terminar monitoreo"
        ),
    )


async def cmd_viaje(bot: Bot, chat_id: int, args_text: str):
    for sep in ["→", "->", " a ", " - ", ","]:
        if sep in args_text:
            partes = args_text.split(sep, 1)
            origen, destino = partes[0].strip(), partes[1].strip()
            break
    else:
        await bot.send_message(
            chat_id=chat_id,
            parse_mode=ParseMode.MARKDOWN,
            text="❌ Formato: `/viaje CDMX - Monterrey`",
        )
        return

    await bot.send_message(
        chat_id=chat_id,
        parse_mode=ParseMode.MARKDOWN,
        text=f"🔍 Calculando ruta *{origen}* - *{destino}*...",
    )

    resultado = await asyncio.get_event_loop().run_in_executor(
        None, calcular_ruta_y_regiones, origen, destino, GMAPS_KEY
    )

    if resultado.get("error"):
        await bot.send_message(chat_id=chat_id, text=f"❌ {resultado['error']}")
        return

    guardar_viaje(chat_id, {"origen": origen, "destino": destino, **resultado})

    regiones_info = get_regions_info(resultado["regiones"])
    regiones_txt = " → ".join(f"{r['emoji']} {r['nombre']}" for r in regiones_info)

    await bot.send_message(
        chat_id=chat_id,
        parse_mode=ParseMode.MARKDOWN,
        text=(
            f"✅ *Viaje iniciado*\n\n"
            f"📍 *{resultado['origen_fmt']}*\n"
            f"🏁 *{resultado['destino_fmt']}*\n\n"
            f"📏 Distancia: *{str(resultado['distancia_km']) + ' km' if resultado['distancia_km'] else 'N/D'}*\n"
            f"⏱ Tiempo: *{str(resultado['duracion_hrs']) + ' hrs' if resultado['duracion_hrs'] else 'N/D'}*\n\n"
            f"🗺 Regiones monitoreadas:\n{regiones_txt}\n\n"
            f"📡 Recibirás alertas automáticas cada 30 min.\n"
            f"Usa /alertas para consultar ahora mismo."
        ),
    )


async def cmd_alertas(bot: Bot, chat_id: int):
    viaje = get_viaje(chat_id)
    if not viaje:
        await bot.send_message(
            chat_id=chat_id,
            parse_mode=ParseMode.MARKDOWN,
            text="❌ Sin viaje activo. Usa `/viaje ORIGEN - DESTINO`",
        )
        return

    await bot.send_message(chat_id=chat_id, text="🔍 Consultando incidentes...")

    regiones = viaje["regiones"]
    waze_inc, capufe_inc = await asyncio.gather(
        get_incidents_for_regions(regiones),
        get_capufe_alerts_for_regions(regiones, REGIONS),
    )
    todos = waze_inc + capufe_inc

    if not todos:
        await bot.send_message(
            chat_id=chat_id,
            parse_mode=ParseMode.MARKDOWN,
            text=f"✅ *Sin incidentes* en tu ruta\n_{viaje['origen']} - {viaje['destino']}_",
        )
        return

    lines = [f"📡 *Incidentes* — {viaje['origen']} - {viaje['destino']}\n"]
    for inc in todos[:10]:
        lines.append(f"{inc['emoji']} *{inc['tipo']}*\n{inc['descripcion']}")
        if inc.get("autor"):
            lines.append(f"_— {inc['autor']}_")
        lines.append("")

    await bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text="\n".join(lines))


async def cmd_trafico(bot: Bot, chat_id: int):
    viaje = get_viaje(chat_id)
    if not viaje:
        await bot.send_message(
            chat_id=chat_id,
            parse_mode=ParseMode.MARKDOWN,
            text="❌ Sin viaje activo. Usa `/viaje ORIGEN - DESTINO`",
        )
        return

    await bot.send_message(chat_id=chat_id, text="🔍 Consultando tráfico...")

    status = await asyncio.get_event_loop().run_in_executor(
        None, get_traffic_status, viaje["origen"], viaje["destino"], GMAPS_KEY
    )
    if status.get("error"):
        await bot.send_message(chat_id=chat_id, text=f"❌ {status['error']}")
        return

    nivel = status["nivel"]
    demora = status["demora_min"]
    emoji = EMOJI_TRAFICO[nivel]

    texto = (
        f"{emoji} *Tráfico {nivel.upper()}*\n\n"
        f"📍 {viaje['origen']} - 🏁 {viaje['destino']}\n"
        f"⏱ Normal: {status['duracion_normal_min']} min\n"
        f"🚗 Con tráfico: *{status['duracion_trafico_min']} min*"
    )
    if demora > 0:
        texto += f"\n⚠️ Demora: *+{demora} min*"

    await bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=texto)


async def cmd_estado(bot: Bot, chat_id: int):
    viaje = get_viaje(chat_id)
    if not viaje:
        await bot.send_message(
            chat_id=chat_id,
            parse_mode=ParseMode.MARKDOWN,
            text="❌ Sin viaje activo. Usa `/viaje ORIGEN - DESTINO`",
        )
        return

    regiones_info = get_regions_info(viaje["regiones"])
    regiones_txt = "\n".join(f"  {r['emoji']} {r['nombre']}" for r in regiones_info)

    await bot.send_message(
        chat_id=chat_id,
        parse_mode=ParseMode.MARKDOWN,
        text=(
            f"🚛 *Viaje activo*\n\n"
            f"📍 *{viaje['origen']}* - 🏁 *{viaje['destino']}*\n"
            f"📏 {viaje['distancia_km']} km · ⏱ {viaje['duracion_hrs']} hrs\n\n"
            f"🗺 Regiones:\n{regiones_txt}"
        ),
    )


async def cmd_regiones(bot: Bot, chat_id: int):
    viaje = get_viaje(chat_id)
    if viaje:
        regiones_info = get_regions_info(viaje["regiones"])
        lines = [f"🗺 *Regiones en tu ruta*\n"]
        for r in regiones_info:
            lines.append(f"{r['emoji']} *{r['nombre']}*")
            lines.append(f"  {', '.join(r['estados'])}")
            lines.append(f"  Carreteras: {', '.join(r['carreteras_clave'])}")
            lines.append("")
    else:
        lines = ["🗺 *Regiones de México*\n"]
        for r in REGIONS.values():
            lines.append(f"{r['emoji']} *{r['nombre']}*: {', '.join(r['estados'])}")

    await bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text="\n".join(lines))


async def cmd_detener(bot: Bot, chat_id: int):
    viaje = get_viaje(chat_id)
    if not viaje:
        await bot.send_message(chat_id=chat_id, text="ℹ️ No tienes ningún viaje activo.")
        return

    detener_viaje(chat_id)
    await bot.send_message(
        chat_id=chat_id,
        parse_mode=ParseMode.MARKDOWN,
        text=f"🏁 Viaje *{viaje['origen']} - {viaje['destino']}* detenido. ¡Buen viaje! 🚛",
    )
