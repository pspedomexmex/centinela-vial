"""
Endpoint temporal de configuración — úsalo UNA VEZ para registrar el webhook.
Eliminar este archivo después de usarlo.
"""
import os
import sys
import json
import httpx
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SETUP_SECRET = os.environ.get("MONITOR_SECRET", "")  # reutiliza el mismo secreto


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        if query.get("secret", [""])[0] != SETUP_SECRET:
            self._json(401, {"ok": False, "error": "no autorizado"})
            return

        token          = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        webhook_secret = os.environ.get("WEBHOOK_SECRET", "")
        host           = self.headers.get("Host", "")
        webhook_url    = f"https://{host}/api/webhook"

        try:
            r = httpx.post(
                f"https://api.telegram.org/bot{token}/setWebhook",
                data={
                    "url": webhook_url,
                    "secret_token": webhook_secret,
                    "allowed_updates": '["message"]',
                },
                timeout=10,
            )
            self._json(200, {"ok": True, "telegram": r.json(), "webhook_url": webhook_url})
        except Exception as e:
            self._json(500, {"ok": False, "error": str(e)})

    def _json(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode())
