"""
Ejecutar UNA SOLA VEZ después del deploy en Vercel para registrar el webhook.
Uso: TELEGRAM_BOT_TOKEN=xxx VERCEL_URL=https://centinela-vial.vercel.app python setup_webhook.py
"""
import os
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
VERCEL_URL = os.environ["VERCEL_URL"].rstrip("/")
WEBHOOK_URL = f"{VERCEL_URL}/api/webhook"

resp = requests.post(
    f"https://api.telegram.org/bot{TOKEN}/setWebhook",
    json={"url": WEBHOOK_URL, "drop_pending_updates": True},
)
data = resp.json()
if data.get("ok"):
    print(f"✅ Webhook registrado: {WEBHOOK_URL}")
else:
    print(f"❌ Error: {data}")
