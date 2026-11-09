"""
Centinela Vial — Listener persistente de comandos (long-polling 24/7).

A diferencia de `bot/poll.py` (un solo sondeo por corrida, pensado para cron),
este script se queda ESCUCHANDO de forma continua. Está hecho para correr como
servicio permanente (systemd) en una maquina siempre encendida, por ejemplo una
VM Always-Free de Oracle Cloud. Asi el bot responde a los comandos al instante,
en vez de "por lotes" cada varios minutos.

Por que existe:
  GitHub Actions (cron) no sirve para un bot de comandos en tiempo real: las
  corridas programadas se retrasan o se descartan, y cada corrida solo escucha
  unos segundos. El *monitor* de alertas (monitor/run.py) si puede vivir en
  cron, pero el bot de comandos necesita un proceso que escuche siempre.

Seguridad:
  - El token se lee SIEMPRE de la variable de entorno TELEGRAM_BOT_TOKEN.
  - Solo hace llamadas SALIENTES a la API de Telegram (getUpdates); no expone
    ningun endpoint entrante, por lo que no hay superficie de ataque entrante.
  - Una sola instancia a la vez por token: dos pollers con el mismo token dan
    error 409 (Conflict). No corras este servicio y poll.py al mismo tiempo.
"""
import os
import sys
import json
import asyncio
import logging

# Permitir ejecutar como script suelto (python bot/run_polling.py).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Bot
from telegram.error import Conflict, NetworkError, TimedOut, RetryAfter

from bot.dispatch import dispatch

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("centinela.bot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# El offset (ultimo update procesado) se guarda localmente para no reprocesar
# mensajes tras un reinicio del servicio.
STATE_DIR = os.environ.get("STATE_DIR", "state")
_OFFSET_PATH = os.path.join(STATE_DIR, "offset.json")

# Long-polling: segundos que Telegram mantiene la conexion abierta esperando
# mensajes. 50 s es el valor tipico recomendado (menos requests, igual de veloz).
_TIMEOUT = int(os.environ.get("POLL_TIMEOUT_SEG", "50"))


def _leer_offset() -> int | None:
    """Ultimo update_id procesado + 1. None si es la primera vez."""
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
    os.replace(tmp, _OFFSET_PATH)  # reemplazo atomico


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)

    async with bot:
        # getUpdates y webhook son excluyentes: aseguramos que no haya webhook.
        try:
            await bot.delete_webhook(drop_pending_updates=False)
        except Exception as e:
            logger.warning(f"No se pudo eliminar webhook (quiza no habia): {e}")

        offset = _leer_offset()
        logger.info(f"Listener persistente iniciado. Offset previo: {offset}")

        # Bucle infinito: el servicio escucha 24/7. systemd lo reinicia si cae.
        while True:
            try:
                updates = await bot.get_updates(
                    offset=offset,
                    timeout=_TIMEOUT,
                    allowed_updates=["message", "edited_message"],
                )
            except RetryAfter as e:
                logger.warning(f"RetryAfter: esperando {e.retry_after}s")
                await asyncio.sleep(float(e.retry_after))
                continue
            except Conflict:
                # Otro getUpdates activo con el mismo token (p. ej. una corrida
                # vieja del workflow, o una segunda instancia). Esperar y seguir.
                logger.error("409 Conflict: otro poller usa este token. Espero 15s.")
                await asyncio.sleep(15)
                continue
            except (NetworkError, TimedOut) as e:
                logger.warning(f"Red/timeout: {e}. Reintento en 3s.")
                await asyncio.sleep(3)
                continue
            except Exception as e:  # noqa: BLE001 — el servicio no debe morir por un error aislado
                logger.exception(f"Error inesperado en get_updates: {e}")
                await asyncio.sleep(5)
                continue

            for upd in updates:
                try:
                    await dispatch(bot, upd.to_dict())
                except Exception as e:  # noqa: BLE001 — un comando con error no debe tumbar el bot
                    logger.exception(f"Error despachando update {upd.update_id}: {e}")
                # Confirmamos el update (avanza el offset) aunque su handler falle,
                # para no quedarnos atascados reprocesando el mismo mensaje.
                offset = upd.update_id + 1
                _guardar_offset(offset)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Listener detenido por el usuario.")
