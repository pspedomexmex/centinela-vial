"""
Handlers del bot de Telegram.
"""
import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from regions.route_parser import calcular_ruta_y_regiones
from regions.mexico_regions import REGIONS, get_regions_info
from sources.waze_incidents import get_incidents_for_regions
from sources.capufe_monitor import get_capufe_alerts_for_regions
from sources.twitter_monitor import get_tweets_for_regions
from sources.gmaps_traffic import get_traffic_status, EMOJI_TRAFICO
from db.trips import guardar_viaje, get_viaje, detener_viaje

logger = logging.getLogger(__name__)

GMAPS_KEY = os.environ["GMAPS_KEY"]
TWITTER_BEARER = os.environ.get("TWITTER_BEARER_TOKEN", "")


# ─── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    texto = (
        "🚛 *Centinela Vial* — Monitor de rutas para transporte de carga\n\n"
        "Comandos disponibles:\n"
        "• `/viaje ORIGEN → DESTINO` — Iniciar monitoreo de ruta\n"
        "  Ej: `/viaje CDMX → Monterrey`\n\n"
        "• `/estado` — Ver estado actual del viaje activo\n"
        "• `/alertas` — Consultar incidentes ahora\n"
        "• `/trafico` — Ver estado del tráfico\n"
        "• `/regiones` — Ver regiones que cubre tu ruta\n"
        "• `/detener` — Terminar monitoreo del viaje\n"
        "• `/ayuda` — Esta ayuda\n\n"
        "📡 Fuentes: Google Maps · Waze · CAPUFE/SCT · X/Twitter"
    )
    await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)


# ─── /viaje ─────────────────────────────────────────────────────────────────

async def cmd_viaje(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args_raw = " ".join(ctx.args) if ctx.args else ""

    # Parsear "ORIGEN → DESTINO" o "ORIGEN - DESTINO" o "ORIGEN a DESTINO"
    for sep in ["→", "->", " a ", " - ", ","]:
        if sep in args_raw:
            partes = args_raw.split(sep, 1)
            origen = partes[0].strip()
            destino = partes[1].strip()
            break
    else:
        await update.message.reply_text(
            "❌ Formato: `/viaje CDMX → Monterrey`\n"
            "Separa origen y destino con → o -",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not origen or not destino:
        await update.message.reply_text("❌ Debes indicar origen y destino.")
        return

    msg = await update.message.reply_text(
        f"🔍 Calculando ruta *{origen}* → *{destino}*...",
        parse_mode=ParseMode.MARKDOWN,
    )

    resultado = await asyncio.get_event_loop().run_in_executor(
        None, calcular_ruta_y_regiones, origen, destino, GMAPS_KEY
    )

    if resultado.get("error"):
        await msg.edit_text(f"❌ Error calculando ruta: {resultado['error']}")
        return

    # Guardar viaje
    guardar_viaje(chat_id, {
        "origen": origen,
        "destino": destino,
        **resultado,
    })

    regiones_info = get_regions_info(resultado["regiones"])
    regiones_txt = " → ".join(f"{r['emoji']} {r['nombre']}" for r in regiones_info)

    texto = (
        f"✅ *Viaje iniciado*\n\n"
        f"📍 *{resultado['origen_fmt']}*\n"
        f"🏁 *{resultado['destino_fmt']}*\n\n"
        f"📏 Distancia: *{resultado['distancia_km']} km*\n"
        f"⏱ Tiempo estimado: *{resultado['duracion_hrs']} hrs*\n\n"
        f"🗺 Regiones monitoreadas:\n{regiones_txt}\n\n"
        f"📡 Recibirás alertas automáticas cada 30 min.\n"
        f"Usa /alertas para consultar ahora mismo."
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📡 Ver alertas ahora", callback_data="alertas_now"),
        InlineKeyboardButton("🛑 Detener", callback_data="detener_viaje"),
    ]])

    await msg.edit_text(texto, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


# ─── /alertas ───────────────────────────────────────────────────────────────

async def cmd_alertas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    viaje = get_viaje(chat_id)

    if not viaje:
        await update.message.reply_text(
            "❌ No tienes un viaje activo. Usa `/viaje ORIGEN → DESTINO`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    msg = await update.message.reply_text("🔍 Consultando incidentes en tu ruta...")

    regiones = viaje["regiones"]

    waze_inc, capufe_inc, twitter_inc = await asyncio.gather(
        get_incidents_for_regions(regiones),
        get_capufe_alerts_for_regions(regiones, REGIONS),
        get_tweets_for_regions(regiones, REGIONS, TWITTER_BEARER),
    )

    todos = waze_inc + capufe_inc + twitter_inc

    if not todos:
        await msg.edit_text(
            f"✅ *Sin incidentes* reportados en tu ruta\n"
            f"_{viaje['origen']} → {viaje['destino']}_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    lines = [f"📡 *Incidentes en ruta* — {viaje['origen']} → {viaje['destino']}\n"]
    for inc in todos[:10]:
        lines.append(f"{inc['emoji']} *{inc['tipo']}*")
        lines.append(inc["descripcion"])
        if inc.get("autor"):
            lines.append(f"_— {inc['autor']}_")
        lines.append("")

    if len(todos) > 10:
        lines.append(f"_... y {len(todos) - 10} incidentes más_")

    await msg.edit_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ─── /trafico ───────────────────────────────────────────────────────────────

async def cmd_trafico(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    viaje = get_viaje(chat_id)

    if not viaje:
        await update.message.reply_text(
            "❌ No tienes un viaje activo. Usa `/viaje ORIGEN → DESTINO`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    msg = await update.message.reply_text("🔍 Consultando tráfico...")

    status = await asyncio.get_event_loop().run_in_executor(
        None, get_traffic_status, viaje["origen"], viaje["destino"], GMAPS_KEY
    )

    if status.get("error"):
        await msg.edit_text(f"❌ Error: {status['error']}")
        return

    nivel = status["nivel"]
    emoji = EMOJI_TRAFICO[nivel]
    demora = status["demora_min"]

    texto = (
        f"{emoji} *Tráfico {nivel.upper()}*\n\n"
        f"📍 {viaje['origen']} → 🏁 {viaje['destino']}\n"
        f"📏 {status['distancia_km']} km\n"
        f"⏱ Normal: {status['duracion_normal_min']} min\n"
        f"🚗 Con tráfico: *{status['duracion_trafico_min']} min*"
    )
    if demora > 0:
        texto += f"\n⚠️ Demora: *+{demora} min*"

    await msg.edit_text(texto, parse_mode=ParseMode.MARKDOWN)


# ─── /estado ────────────────────────────────────────────────────────────────

async def cmd_estado(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    viaje = get_viaje(chat_id)

    if not viaje:
        await update.message.reply_text(
            "❌ No tienes un viaje activo. Usa `/viaje ORIGEN → DESTINO`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    regiones_info = get_regions_info(viaje["regiones"])
    regiones_txt = "\n".join(f"  {r['emoji']} {r['nombre']}" for r in regiones_info)

    texto = (
        f"🚛 *Viaje activo*\n\n"
        f"📍 Origen: *{viaje['origen']}*\n"
        f"🏁 Destino: *{viaje['destino']}*\n"
        f"📏 Distancia: *{viaje['distancia_km']} km*\n"
        f"⏱ Tiempo estimado: *{viaje['duracion_hrs']} hrs*\n\n"
        f"🗺 Regiones monitoreadas:\n{regiones_txt}\n\n"
        f"🕐 Iniciado: {viaje['creado_en'][:16].replace('T', ' ')}"
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📡 Alertas", callback_data="alertas_now"),
        InlineKeyboardButton("🚗 Tráfico", callback_data="trafico_now"),
        InlineKeyboardButton("🛑 Detener", callback_data="detener_viaje"),
    ]])

    await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


# ─── /regiones ──────────────────────────────────────────────────────────────

async def cmd_regiones(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    viaje = get_viaje(chat_id)

    if viaje:
        regiones_info = get_regions_info(viaje["regiones"])
        lines = [f"🗺 *Regiones en tu ruta* — {viaje['origen']} → {viaje['destino']}\n"]
        for r in regiones_info:
            estados = ", ".join(r["estados"])
            carreteras = ", ".join(r["carreteras_clave"])
            lines.append(f"{r['emoji']} *{r['nombre']}*")
            lines.append(f"  Estados: {estados}")
            lines.append(f"  Carreteras: {carreteras}")
            lines.append("")
    else:
        lines = ["🗺 *Regiones de México (transporte de carga)*\n"]
        for key, r in REGIONS.items():
            estados = ", ".join(r["estados"])
            lines.append(f"{r['emoji']} *{r['nombre']}*: {estados}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ─── /detener ────────────────────────────────────────────────────────────────

async def cmd_detener(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    viaje = get_viaje(chat_id)

    if not viaje:
        await update.message.reply_text("ℹ️ No tienes ningún viaje activo.")
        return

    detener_viaje(chat_id)
    await update.message.reply_text(
        f"🏁 Viaje *{viaje['origen']} → {viaje['destino']}* detenido.\n"
        "Monitoreo cancelado. ¡Buen viaje! 🚛",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── Callbacks inline ────────────────────────────────────────────────────────

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "alertas_now":
        update._effective_message = query.message
        update._effective_chat = query.message.chat
        await cmd_alertas(update, ctx)
    elif query.data == "trafico_now":
        update._effective_message = query.message
        update._effective_chat = query.message.chat
        await cmd_trafico(update, ctx)
    elif query.data == "detener_viaje":
        update._effective_message = query.message
        update._effective_chat = query.message.chat
        await cmd_detener(update, ctx)
