"""
Centinela Vial — Sondeo de comandos por lotes (getUpdates) para GitHub Actions.

En la arquitectura v2 no hay servidor ni webhook: un workflow ejecuta este
script cada pocos minutos. El script:
  1. Elimina cualquier webhook previo (getUpdates y webhook son excluyentes).
  2. Pide a Telegram los mensajes pendientes (getUpdates) desde un 'offset'
     que se persiste en state/offset.json para no reprocesar.
  3. Despacha cada comando a su handler (bot/dispatch.py) y responde.
  4. Guarda el nuevo offset.

Seguridad:
  - El token se lee SIEMPRE de la variable de entorno TELEGRAM_BOT_TOKEN.
  - No se expone ningún endpoint público (a diferencia de un webhook), por lo
    que no hay superficie de ataque entrante: Telegram sólo es consultado por
    nosotros, de forma saliente.
"""
import os
import sys
import json
import asyncio
import logging

# Permitir ejecutar como script suelto (python bot/poll.py).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Bot

from bot.dispatch import dispatch

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# El offset vive junto al resto del estado versionado.
STATE_DIR    = os.environ.get("STATE_DIR", "state")
_OFFSET_PATH = os.path.join(STATE_DIR, "offset.json")

# Cuántos segundos esperar a que lleguen updates (long-polling corto).
_TIMEOUT = int(os.environ.get("POLL_TIMEOUT_SEG", "20"))


def _leer_offset() -> int | None:
    """Último update_id procesado + 1. None si es la primera corrida."""
    try:
        with open(_OFFSET_PATH, encoding="utf-8") as f:
            return json.load(f).get("offset")
    except (OSError, json.JSONDecodeError):
        return None


def _guardar_offset(offset: int) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = _OFFSET_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"offset": offset}, f)
    os.replace(tmp, _OFFSET_PATH)  # reemplazo atómico


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)

    async with bot:
        # getUpdates y webhook son excluyentes: aseguramos que no haya webhook.
        try:
            await bot.delete_webhook(drop_pending_updates=False)
        except Exception as e:
            logger.warning(f"No se pudo eliminar webhook (quizá no había): {e}")

        offset = _leer_offset()
        logger.info(f"Sondeo iniciado. Offset previo: {offset}")

        updates = await bot.get_updates(
            offset=offset,
            timeout=_TIMEOUT,
            allowed_updates=["message", "edited_message"],
        )

        if not updates:
            logger.info("Sin mensajes nuevos.")
            return

        logger.info(f"Procesando {len(updates)} update(s)...")
        ultimo_id = offset or 0
        for upd in updates:
            await dispatch(bot, upd.to_dict())
            ultimo_id = max(ultimo_id, upd.update_id)

        # Guardar offset = último procesado + 1 (confirma los updates a Telegram).
        _guardar_offset(ultimo_id + 1)
        logger.info(f"Listo. Nuevo offset: {ultimo_id + 1}")


if __name__ == "__main__":
    asyncio.run(main())
