"""
Despachador de comandos de Telegram — independiente del transporte.

Toma un 'update' crudo de la API de Telegram y lo enruta al handler
correspondiente. Lo usa bot/poll.py (sondeo por getUpdates en GitHub Actions).

Se separó aquí para no acoplar el ruteo a un servidor webhook: en la
arquitectura v2 no hay servidor, el sondeo por lotes importa esta misma función.
"""
import logging
from telegram import Bot, Update

from bot.handlers import (
    cmd_start, cmd_viaje, cmd_alertas, cmd_trafico,
    cmd_estado, cmd_regiones, cmd_detener, cmd_ruta, cmd_pregunta,
    cmd_escaneo, cmd_zona, cmd_rcpn,
)

logger = logging.getLogger(__name__)


async def dispatch(bot: Bot, update_data: dict) -> None:
    """
    Procesa un update de Telegram y ejecuta el comando correspondiente.
    Silencioso ante updates sin texto (p. ej. estados, ediciones de media).
    """
    update = Update.de_json(update_data, bot)

    msg = update.message or update.edited_message
    if not msg or not msg.text:
        return

    text = msg.text.strip()
    chat_id = msg.chat_id

    # Extraer comando quitando el posible sufijo @NombreDelBot.
    primera = text.split()[0]
    cmd = primera.split("@")[0].lower() if text.startswith("/") else ""
    # Argumentos = todo lo que sigue al comando.
    args = text[len(primera):].strip() if text.startswith("/") else ""

    try:
        if cmd in ("/start", "/ayuda"):
            await cmd_start(bot, chat_id)
        elif cmd == "/viaje":
            await cmd_viaje(bot, chat_id, args)
        elif cmd == "/alertas":
            await cmd_alertas(bot, chat_id)
        elif cmd == "/ruta":
            await cmd_ruta(bot, chat_id)
        elif cmd == "/trafico":
            await cmd_trafico(bot, chat_id)
        elif cmd == "/estado":
            await cmd_estado(bot, chat_id)
        elif cmd == "/regiones":
            await cmd_regiones(bot, chat_id)
        elif cmd == "/detener":
            await cmd_detener(bot, chat_id)
        elif cmd == "/escaneo":
            await cmd_escaneo(bot, chat_id)
        elif cmd == "/zona":
            await cmd_zona(bot, chat_id)
        elif cmd == "/rcpn":
            await cmd_rcpn(bot, chat_id)
        elif not cmd:
            # Texto libre (sin comando) → agente IA (Groq).
            await cmd_pregunta(bot, chat_id, text)
        else:
            await bot.send_message(
                chat_id=chat_id,
                text="❓ Comando no reconocido. Usa /ayuda para ver la lista.",
            )
    except Exception as e:
        # Un fallo en un comando no debe tumbar el ciclo de sondeo completo.
        logger.error(f"Error despachando '{cmd}' (chat {chat_id}): {e}")
