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
from sources.tomtom_incidents import (
    get_incidents_for_city_route as _city_incidents,
    get_incidents_for_route as _region_incidents,
)
from sources.tomtom_flow import (
    get_flow_alerts_for_city_route as _city_flow,
    get_flow_alerts_for_regions as _region_flow,
    get_flow_speeds_dict as _get_flow_speeds,
)
from sources.openmeteo import (
    get_weather_alerts_for_city_route as _city_weather,
    get_weather_alerts_for_regions as _region_weather,
)
from sources.nitter_monitor import (
    get_tweets_for_city_route as _city_tweets,
    get_tweets_for_regions as _region_tweets,
)
from sources.capufe_monitor import get_capufe_alerts_for_regions
from sources.escaneo_carreteras import escaneo_nacional
from sources.gmaps_traffic import get_traffic_status, EMOJI_TRAFICO
from db.supabase_client import (
    guardar_viaje, get_viaje, detener_viaje,
    actualizar_cierres, limpiar_cierres_viaje,
    registrar_incidentes_historico,
)

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
            "• `/escaneo` — Panorama vial nacional (27 tramos)\n"
            "• `/alertas` — Incidentes en tu ruta ahora\n"
            "• `/ruta` — Desglose de tramos, km y tiempo\n"
            "• `/trafico` — Estado del tráfico\n"
            "• `/estado` — Resumen del viaje activo\n"
            "• `/regiones` — Regiones que cubre tu ruta\n"
            "• `/detener` — Terminar monitoreo\n\n"
            "📊 `/dashboard` — Ver datos históricos en tiempo real"
        ),
    )


async def cmd_dashboard(bot: Bot, chat_id: int):
    await bot.send_message(
        chat_id=chat_id,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=False,
        text=(
            "📊 *Centinela Vial — Dashboard de Tesis*\n\n"
            "Visualiza incidentes, flujo vial y clima acumulados:\n\n"
            "🔗 [centinela\\-vial\\.vercel\\.app/dashboard](https://centinela-vial.vercel.app/dashboard)\n\n"
            "• Incidentes por tipo y carretera\n"
            "• Flujo vial por ciudad\n"
            "• Distribución por hora y día\n"
            "• Mapa de incidentes con coordenadas\n"
            "• Tabla de últimos registros\n\n"
            "_Datos actualizados 3 veces al día — 06:00, 14:00, 22:00 MX_"
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

    try:
        # Pasada 1: ruta estática (instantánea)
        resultado = calcular_ruta_y_regiones(origen, destino, GMAPS_KEY)

        if resultado.get("error"):
            await bot.send_message(chat_id=chat_id, text=f"❌ {resultado['error']}")
            return

        # Pasada 2: tráfico real con TomTom Flow (si hay city_path)
        flow_note = ""
        city_path_inicial = resultado.get("city_path") or []
        if city_path_inicial:
            try:
                flow_speeds = await _get_flow_speeds(city_path_inicial)
                if flow_speeds:
                    resultado_rt = calcular_ruta_y_regiones(origen, destino, GMAPS_KEY, flow_overrides=flow_speeds)
                    if resultado_rt and not resultado_rt.get("error"):
                        hrs_est  = resultado["duracion_hrs"]
                        hrs_real = resultado_rt["duracion_hrs"]
                        diff = round(hrs_real - hrs_est, 1)
                        if resultado_rt.get("city_path") != city_path_inicial:
                            flow_note = "\n⚡ _Ruta ajustada por tráfico actual_"
                        elif diff > 0:
                            flow_note = f"\n⚡ _Tráfico actual: +{diff} hrs de demora_"
                        elif diff < 0:
                            flow_note = f"\n⚡ _Tráfico fluye bien: {diff} hrs menos_"
                        else:
                            flow_note = "\n⚡ _Tráfico normal en la ruta_"
                        resultado = resultado_rt
            except Exception:
                pass  # flow falla silenciosamente, no bloqueamos el viaje

        guardar_viaje(chat_id, {"origen": origen, "destino": destino, **resultado})

        from regions.city_graph import CITY_LABELS
        regiones_info = get_regions_info(resultado["regiones"])
        regiones_txt = " → ".join(f"{r['emoji']} {r['nombre']}" for r in regiones_info)

        dist = f"{resultado['distancia_km']} km" if resultado["distancia_km"] else "N/D"
        dur = f"{resultado['duracion_hrs']} hrs" if resultado["duracion_hrs"] else "N/D"

        city_path = resultado.get("city_path") or []
        path_txt = ""
        if len(city_path) > 2:
            vias = " → ".join(CITY_LABELS.get(c, c.title()) for c in city_path[1:-1])
            path_txt = f"\n🛣 Vía: _{vias}_\n"

        await bot.send_message(
            chat_id=chat_id,
            parse_mode=ParseMode.MARKDOWN,
            text=(
                f"✅ *Viaje iniciado*\n\n"
                f"📍 *{resultado['origen_fmt']}*\n"
                f"🏁 *{resultado['destino_fmt']}*\n"
                f"{path_txt}\n"
                f"📏 Distancia: *{dist}*\n"
                f"⏱ Tiempo: *{dur}*{flow_note}\n\n"
                f"🗺 Regiones monitoreadas:\n{regiones_txt}\n\n"
                f"📡 Recibirás alertas automáticas cada 30 min.\n"
                f"Usa /alertas para consultar ahora mismo."
            ),
        )
    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"❌ Error: {e}")


async def cmd_alertas(bot: Bot, chat_id: int):
    viaje = get_viaje(chat_id)
    if not viaje:
        await bot.send_message(
            chat_id=chat_id,
            parse_mode=ParseMode.MARKDOWN,
            text="❌ Sin viaje activo. Usa `/viaje ORIGEN - DESTINO`",
        )
        return

    await bot.send_message(chat_id=chat_id, text="🔍 Consultando ruta...")

    city_path = viaje.get("city_path")
    regiones  = viaje["regiones"]

    # Lanzar las 3 fuentes en paralelo
    if city_path:
        inc_task     = _city_incidents(city_path)
        flow_task    = _city_flow(city_path)
        weather_task = _city_weather(city_path)
        tweet_task   = _city_tweets(city_path)
    else:
        inc_task     = _region_incidents(regiones)
        flow_task    = _region_flow(regiones)
        weather_task = _region_weather(regiones)
        tweet_task   = _region_tweets(regiones)

    (tomtom_inc, _), flow_inc, weather_inc, (tweet_inc, nitter_up) = await asyncio.gather(
        inc_task,
        flow_task,
        weather_task,
        tweet_task,
    )

    # Guardar histórico para dataset de tesis
    registrar_incidentes_historico(
        tomtom_inc + flow_inc + weather_inc,
        origen=viaje.get("origen", ""),
        destino=viaje.get("destino", ""),
        city_path=city_path,
    )

    # Sincronizar cierres y detectar reaperturas
    cierres_actuales = {
        inc["cierre_hash"]: inc["descripcion"]
        for inc in tomtom_inc
        if inc.get("cierre_hash")
    }
    reabiertos = actualizar_cierres(chat_id, cierres_actuales)

    header = f"📡 *{viaje['origen']} → {viaje['destino']}*\n"
    lines  = [header]
    hay_algo = False

    if reabiertos:
        hay_algo = True
        lines.append("✅ *Carreteras reabiertas*")
        for desc in reabiertos:
            lines.append(f"✅ _{desc}_")
        lines.append("")

    # ── Sección 1: Incidentes críticos ─────────────────────────
    if tomtom_inc:
        hay_algo = True
        lines.append("🚨 *Incidentes en carretera*")
        for inc in tomtom_inc[:6]:
            hora = f" · _{inc['hora']} h_" if inc.get("hora") else ""
            lines.append(f"{inc['emoji']} *{inc['tipo']}*{hora}")
            lines.append(f"_{inc['descripcion']}_")
            if inc.get("coords"):
                lat, lon = inc["coords"]
                lines.append(f"📍 [Ver en mapa](https://maps.google.com/?q={lat},{lon})")
            lines.append("")
    else:
        lines.append("✅ Sin incidentes en carretera\n")

    # ── Sección 2: Flujo vial ───────────────────────────────────
    if flow_inc:
        hay_algo = True
        lines.append("🚦 *Flujo vial*")
        for inc in flow_inc[:4]:
            lines.append(f"{inc['emoji']} {inc['descripcion']}")
        lines.append("")
    else:
        lines.append("🟢 Flujo vial normal\n")

    # ── Sección 3: Clima en ruta ────────────────────────────────
    if weather_inc:
        hay_algo = True
        lines.append("🌦 *Clima en ruta*")
        for inc in weather_inc[:4]:
            lines.append(f"{inc['emoji']} {inc['descripcion']}")
        lines.append("")
    else:
        lines.append("☀️ Clima favorable en toda la ruta")

    # ── Sección 4: Avisos de X/Twitter ─────────────────────────
    if tweet_inc:
        hay_algo = True
        fuente_label = tweet_inc[0].get("fuente", "Noticias")
        lines.append(f"\n📰 *Noticias viales ({fuente_label})*")
        for inc in tweet_inc[:4]:
            autor = f"  `{inc['autor']}`" if inc.get("autor") else ""
            lines.append(f"{inc['emoji']} {inc['descripcion']}{autor}")
        lines.append("")
    elif not nitter_up:
        lines.append("📰 _Noticias viales no disponibles_\n")

    await bot.send_message(
        chat_id=chat_id,
        parse_mode=ParseMode.MARKDOWN,
        text="\n".join(lines),
    )


async def cmd_ruta(bot: Bot, chat_id: int):
    viaje = get_viaje(chat_id)
    if not viaje:
        await bot.send_message(
            chat_id=chat_id,
            parse_mode=ParseMode.MARKDOWN,
            text="❌ Sin viaje activo. Usa `/viaje ORIGEN - DESTINO`",
        )
        return

    city_path = viaje.get("city_path")
    if not city_path or len(city_path) < 2:
        await bot.send_message(
            chat_id=chat_id,
            text="ℹ️ Ruta sin desglose de ciudades disponible.",
        )
        return

    from regions.city_graph import CITY_LABELS, CITY_EDGES, EDGE_KM, EDGE_TIME_MIN

    lines = [f"🛣 *Ruta: {viaje['origen']} → {viaje['destino']}*\n"]
    total_km = 0
    total_min = 0

    for i in range(len(city_path) - 1):
        a, b = city_path[i], city_path[i + 1]
        label_a = CITY_LABELS.get(a, a.title())
        label_b = CITY_LABELS.get(b, b.title())
        hw  = CITY_EDGES.get(a, {}).get(b, "")
        km  = EDGE_KM.get(a, {}).get(b, 0)
        min_= EDGE_TIME_MIN.get(a, {}).get(b, 0)
        total_km  += km
        total_min += min_
        hrs_tramo = f"{min_ // 60}h {min_ % 60:02d}m" if min_ >= 60 else f"{min_}min"
        hw_txt = f" `{hw}`" if hw else ""
        lines.append(f"📍 *{label_a}* →{hw_txt} *{label_b}*")
        lines.append(f"   {km} km · {hrs_tramo}")

    hrs_t = total_min // 60
    min_t = total_min % 60
    lines.append(f"\n📏 Total: *{total_km} km* · ⏱ *{hrs_t}h {min_t:02d}m*")

    await bot.send_message(
        chat_id=chat_id,
        parse_mode=ParseMode.MARKDOWN,
        text="\n".join(lines),
    )


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

    city_path = viaje.get("city_path")

    # Intento con Google Maps si hay key
    if GMAPS_KEY:
        status = await asyncio.get_event_loop().run_in_executor(
            None, get_traffic_status, viaje["origen"], viaje["destino"], GMAPS_KEY
        )
        if not status.get("error"):
            nivel  = status["nivel"]
            demora = status["demora_min"]
            emoji  = EMOJI_TRAFICO[nivel]
            texto  = (
                f"{emoji} *Tráfico {nivel.upper()}*\n\n"
                f"📍 {viaje['origen']} - 🏁 {viaje['destino']}\n"
                f"⏱ Normal: {status['duracion_normal_min']} min\n"
                f"🚗 Con tráfico: *{status['duracion_trafico_min']} min*"
            )
            if demora > 0:
                texto += f"\n⚠️ Demora: *+{demora} min*"
            await bot.send_message(chat_id=chat_id, parse_mode=ParseMode.MARKDOWN, text=texto)
            return

    # Fallback: TomTom Flow sobre las ciudades de la ruta
    if city_path:
        flow_alerts = await _city_flow(city_path)
    else:
        flow_alerts = await _region_flow(viaje.get("regiones", []))

    if not flow_alerts:
        await bot.send_message(
            chat_id=chat_id,
            parse_mode=ParseMode.MARKDOWN,
            text=(
                f"🟢 *Tráfico LIBRE*\n\n"
                f"📍 {viaje['origen']} - 🏁 {viaje['destino']}\n"
                f"_Sin congestionamientos detectados en la ruta_"
            ),
        )
        return

    lines = [f"🚦 *Flujo vial — {viaje['origen']} → {viaje['destino']}*\n"]
    for a in flow_alerts[:6]:
        lines.append(f"{a['emoji']} {a['descripcion']}")
    await bot.send_message(
        chat_id=chat_id,
        parse_mode=ParseMode.MARKDOWN,
        text="\n".join(lines),
    )


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
    limpiar_cierres_viaje(chat_id)
    await bot.send_message(
        chat_id=chat_id,
        parse_mode=ParseMode.MARKDOWN,
        text=f"🏁 Viaje *{viaje['origen']} - {viaje['destino']}* detenido. ¡Buen viaje! 🚛",
    )


async def cmd_escaneo(bot: Bot, chat_id: int):
    await bot.send_message(chat_id=chat_id, text="📡 Escaneando carreteras nacionales...")

    try:
        resultados = await escaneo_nacional()
    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"❌ Error en escaneo: {e}")
        return

    if not resultados:
        await bot.send_message(chat_id=chat_id, text="⚠️ Sin datos disponibles (verifica TOMTOM_KEY).")
        return

    from datetime import datetime, timezone, timedelta
    hora_mx = datetime.now(timezone(timedelta(hours=-6))).strftime("%H:%M")

    _EMOJI = {"MUY_LENTO": "🔴", "LENTO": "🟠", "MODERADO": "🟡", "NORMAL": "🟢", "sin_datos": "⚫"}

    con_problemas = [r for r in resultados if r["sev"] > 0]
    libres        = [r for r in resultados if r["sev"] == 0 and r["nivel"] == "NORMAL"]
    sin_datos     = [r for r in resultados if r["nivel"] == "sin_datos"]

    lines = [f"📡 *Escaneo vial — México* · {hora_mx} h\n"]

    # Tramos con problemas (máx 10 para no exceder límite de Telegram)
    for r in con_problemas[:10]:
        emoji = _EMOJI[r["nivel"]]
        hw_txt = f" `{r['hw']}`" if r["hw"] else ""
        vel_txt = ""
        if r["velocidad"] and r["libre"] and r["ratio"] is not None:
            pct = int((1 - r["ratio"]) * 100)
            vel_txt = f" · {r['velocidad']} km/h (−{pct}%)"
        lines.append(f"{emoji} *{r['nombre']}*{hw_txt}{vel_txt}")
        for inc in r["incidentes"]:
            lines.append(f"   {inc}")

    # Resumen de libres
    if libres:
        names = ", ".join(r["nombre"] for r in libres)
        lines.append(f"\n🟢 *{len(libres)} tramos libres* — {names}")

    if sin_datos:
        lines.append(f"\n⚫ _{len(sin_datos)} tramos sin datos de TomTom_")

    if not con_problemas:
        lines.append("\n✅ *Todas las carreteras fluyen con normalidad*")

    await bot.send_message(
        chat_id=chat_id,
        parse_mode=ParseMode.MARKDOWN,
        text="\n".join(lines),
    )


async def cmd_pregunta(bot: Bot, chat_id: int, text: str):
    from bot.agent import run_agent
    await bot.send_message(chat_id=chat_id, text="🤔 Consultando...")
    try:
        respuesta = await run_agent(chat_id, text)
        await bot.send_message(
            chat_id=chat_id,
            parse_mode=ParseMode.MARKDOWN,
            text=respuesta,
        )
    except Exception as e:
        logger.error(f"Error en agente IA: {e}")
        await bot.send_message(chat_id=chat_id, text=f"❌ Error del agente: {e}")
