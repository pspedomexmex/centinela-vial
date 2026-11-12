"""
Endpoint de monitoreo para Vercel (serverless) — Centinela Vial.

Un programador externo gratuito (p. ej. cron-job.org) hace GET a esta URL cada
30 minutos. La función lee los viajes activos del estado COMPARTIDO (Upstash
Redis) y envía a Telegram las alertas nuevas de cada ruta. Así las alertas
automáticas funcionan sin servidor 24/7 y sin depender de la frecuencia (poco
fiable) de los cron de GitHub Actions.

Seguridad (prioritaria):
  - Se exige un secreto MONITOR_SECRET en la petición (query ?secret=... o
    cabecera X-Monitor-Secret). Sin él se responde 401. Esto evita que un
    tercero dispare el monitoreo y agote tu cuota gratuita de TomTom.
  - El token de Telegram y las credenciales de Redis se leen de variables de
    entorno; nunca van en el código.
  - Solo hace llamadas salientes (Telegram, TomTom, Redis); el endpoint en sí
    no recibe datos del usuario más allá del secreto.
"""
import os
import sys
import json
import asyncio
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Permitir importar el paquete del proyecto desde la raíz del repo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MONITOR_SECRET = os.environ.get("MONITOR_SECRET", "")


def _autorizado(path: str, headers) -> bool:
    """Valida el secreto por query string o por cabecera."""
    if not MONITOR_SECRET:
        # Sin secreto configurado, por seguridad NO se ejecuta.
        return False
    query = parse_qs(urlparse(path).query)
    por_query = (query.get("secret", [""])[0] == MONITOR_SECRET)
    por_header = (headers.get("X-Monitor-Secret", "") == MONITOR_SECRET)
    return por_query or por_header


class handler(BaseHTTPRequestHandler):
    def _responder(self, codigo: int, cuerpo: dict) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        if not _autorizado(self.path, self.headers):
            self._responder(401, {"ok": False, "error": "no autorizado"})
            return
        try:
            from monitor.run import run_monitor
            resumen = asyncio.run(run_monitor())
            self._responder(200, resumen)
        except Exception as e:  # noqa: BLE001
            print(f"[monitor] error: {e}", file=sys.stderr)
            self._responder(500, {"ok": False, "error": str(e)})

    # Algunos cron hacen POST; lo tratamos igual que GET.
    do_POST = do_GET
