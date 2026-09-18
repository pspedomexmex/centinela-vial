"""
Centinela Vial — Bot Telegram para monitoreo de rutas de transporte de carga en México.
"""
import os
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
)

from bot.handlers import (
    cmd_start, cmd_viaje, cmd_alertas, cmd_trafico,
    cmd_estado, cmd_regiones, cmd_detener, callback_handler,
)
from scheduler.trip_monitor import check_and_notify, reporte_trafico_periodico
from db.trips import init_db

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GMAPS_KEY = os.environ["GMAPS_KEY"]
TWITTER_BEARER = os.environ.get("TWITTER_BEARER_TOKEN", "")

CHECK_INTERVAL_MIN = int(os.environ.get("CHECK_INTERVAL_MIN", "30"))
TRAFFIC_INTERVAL_MIN = int(os.environ.get("TRAFFIC_INTERVAL_MIN", "60"))


# ── Health server para Hugging Face Spaces (requiere puerto 7860) ─────────────

class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Centinela Vial OK")

    def log_message(self, *args):
        pass  # silenciar logs de HTTP


def _start_health_server():
    port = int(os.environ.get("PORT", 7860))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Health server en puerto {port}")


# ─────────────────────────────────────────────────────────────────────────────

async def job_alertas(ctx):
    await check_and_notify(ctx.bot, GMAPS_KEY, TWITTER_BEARER)


async def job_trafico(ctx):
    await reporte_trafico_periodico(ctx.bot, GMAPS_KEY)


def main():
    init_db()
    _start_health_server()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ayuda", cmd_start))
    app.add_handler(CommandHandler("viaje", cmd_viaje))
    app.add_handler(CommandHandler("alertas", cmd_alertas))
    app.add_handler(CommandHandler("trafico", cmd_trafico))
    app.add_handler(CommandHandler("estado", cmd_estado))
    app.add_handler(CommandHandler("regiones", cmd_regiones))
    app.add_handler(CommandHandler("detener", cmd_detener))
    app.add_handler(CallbackQueryHandler(callback_handler))

    jq = app.job_queue
    jq.run_repeating(job_alertas, interval=CHECK_INTERVAL_MIN * 60, first=60)
    jq.run_repeating(job_trafico, interval=TRAFFIC_INTERVAL_MIN * 60, first=300)

    logger.info("🚛 Centinela Vial arrancando...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
