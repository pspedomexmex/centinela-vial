"""
Vercel serverless webhook — recibe updates de Telegram y despacha comandos.
"""
import json
import os
import asyncio
import logging
from http.server import BaseHTTPRequestHandler

from telegram import Bot, Update

from bot.handlers import (
    cmd_start, cmd_viaje, cmd_alertas, cmd_trafico,
    cmd_estado, cmd_regiones, cmd_detener, cmd_ruta, cmd_pregunta,
    cmd_dashboard, cmd_escaneo, cmd_zona, cmd_rcpn,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]


async def dispatch(update_data: dict):
    bot = Bot(token=BOT_TOKEN)
    update = Update.de_json(update_data, bot)

    msg = update.message or update.edited_message
    if not msg or not msg.text:
        return

    text = msg.text.strip()
    chat_id = msg.chat_id

    # Extraer comando (quitar @CentinelaVialBot si viene con @)
    cmd = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
    args = text[len(text.split()[0]):].strip() if text.startswith("/") else ""

    if cmd in ("/start", "/ayuda"):
        await cmd_start(bot, chat_id)
    elif cmd == "/viaje":
        await cmd_viaje(bot, chat_id, args)
    elif cmd == "/alertas":
        await cmd_alertas(bot, chat_id)
    elif cmd == "/trafico":
        await cmd_trafico(bot, chat_id)
    elif cmd == "/estado":
        await cmd_estado(bot, chat_id)
    elif cmd == "/regiones":
        await cmd_regiones(bot, chat_id)
    elif cmd == "/ruta":
        await cmd_ruta(bot, chat_id)
    elif cmd == "/detener":
        await cmd_detener(bot, chat_id)
    elif cmd == "/dashboard":
        await cmd_dashboard(bot, chat_id)
    elif cmd == "/escaneo":
        await cmd_escaneo(bot, chat_id)
    elif cmd == "/zona":
        await cmd_zona(bot, chat_id)
    elif cmd == "/rcpn":
        await cmd_rcpn(bot, chat_id)
    elif not cmd:
        await cmd_pregunta(bot, chat_id, text)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Centinela Vial OK")

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body)
            asyncio.run(dispatch(data))
        except Exception as e:
            logger.error(f"Error procesando update: {e}")

        # Siempre responder 200 para que Telegram no reintente
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        pass
