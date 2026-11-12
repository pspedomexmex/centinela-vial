"""
Webhook de Telegram para Vercel (serverless) — Centinela Vial.

Telegram hace POST de cada mensaje a esta funcion y el bot responde al instante.
No hay proceso encendido ni cron: ideal para el plan gratis de Vercel (sin tarjeta).

Modo "consulta en vivo" (sin base de datos):
  Los comandos que consultan una API y responden en el momento funcionan tal cual:
  /trafico, /ruta, /escaneo, /zona, /rcpn, /alertas, /regiones, /ayuda, /start.
  El estado se escribe en /tmp (unico directorio escribible en Vercel, y EFIMERO),
  por lo que el seguimiento de viajes activos (/viaje, /estado, /detener) NO
  persiste entre mensajes. Si mas adelante quieres esa memoria, se conecta un
  almacen gratuito (p. ej. Upstash Redis). Ver deploy/VERCEL.md.

Seguridad:
  - El token se lee de la variable de entorno TELEGRAM_BOT_TOKEN.
  - Se verifica el header secreto de Telegram (WEBHOOK_SECRET) para rechazar
    cualquier POST que no provenga de Telegram.
"""
import os
import sys
import json
import asyncio
from http.server import BaseHTTPRequestHandler

# En Vercel solo /tmp es escribible; el estado efimero vive ahi.
os.environ.setdefault("STATE_DIR", "/tmp/state")

# Permitir importar el paquete bot/ desde la raiz del repo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Bot
from bot.dispatch import dispatch

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")


async def _procesar(update: dict) -> None:
    bot = Bot(token=BOT_TOKEN)
    async with bot:
        await dispatch(bot, update)


class handler(BaseHTTPRequestHandler):
    def _responder(self, codigo: int, cuerpo: bytes = b"") -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        if cuerpo:
            self.wfile.write(cuerpo)

    def do_POST(self):
        # 1. Verificar el secreto de Telegram (si esta configurado).
        if WEBHOOK_SECRET:
            recibido = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if recibido != WEBHOOK_SECRET:
                self._responder(401)
                return

        # 2. Leer el update.
        try:
            largo = int(self.headers.get("Content-Length", 0) or 0)
            cuerpo = self.rfile.read(largo) if largo else b"{}"
            update = json.loads(cuerpo.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"[webhook] cuerpo invalido: {e}", file=sys.stderr)
            self._responder(400)
            return

        # 3. Despachar. A Telegram le respondemos 200 SIEMPRE para que no reintente;
        #    cualquier error del handler se registra en los logs de Vercel.
        try:
            asyncio.run(_procesar(update))
        except Exception as e:  # noqa: BLE001
            print(f"[webhook] error procesando update: {e}", file=sys.stderr)

        self._responder(200, b'{"ok":true}')

    def do_GET(self):
        # Health check simple (abrir la URL en el navegador debe mostrar esto).
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Centinela Vial — webhook activo.".encode("utf-8"))
