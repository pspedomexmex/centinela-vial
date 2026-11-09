# Despliegue del bot por Webhook en Vercel (gratis, sin tarjeta)

El bot de comandos corre como una **funcion serverless** (`api/webhook.py`).
Telegram hace POST de cada mensaje a esa URL y el bot responde al instante.
No hay proceso encendido ni cron: perfecto para el plan **Hobby** (gratis).

> **Modo "consulta en vivo" (sin DB).** Funcionan los comandos que consultan y
> responden al momento: `/trafico`, `/ruta`, `/escaneo`, `/zona`, `/rcpn`,
> `/alertas`, `/regiones`, `/ayuda`. El estado se guarda en `/tmp` (efimero en
> Vercel), por lo que el seguimiento de viajes activos (`/viaje`, `/estado`,
> `/detener`) **no persiste** entre mensajes. Para memoria real, conecta un
> almacen gratuito como **Upstash Redis** (ver el final).

---

## 1. Variables de entorno (en Vercel)

Proyecto en Vercel → **Settings → Environment Variables** → agrega:

| Nombre | Valor | Obligatoria |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | tu token **rotado** de @BotFather | ✅ |
| `WEBHOOK_SECRET` | una cadena aleatoria que inventes (p. ej. `openssl rand -hex 16`) | ✅ (seguridad) |
| `TOMTOM_KEY` | API key de TomTom | recomendada |
| `GMAPS_KEY` | API key de Google Maps | opcional |
| `GROQ_API_KEY` | API key de Groq (agente IA) | opcional |
| `TWITTER_BEARER_TOKEN` | Bearer de X/Twitter | opcional |

Marca cada una para **Production** y vuelve a desplegar (Deployments → Redeploy)
para que tomen efecto.

## 2. Verificar que la funcion vive

Abre en el navegador:  `https://<tu-proyecto>.vercel.app/api/webhook`
Debe responder: **"Centinela Vial — webhook activo."**

## 3. Registrar el webhook en Telegram

Una sola vez, desde tu terminal (sustituye `<TOKEN>`, la URL y `<WEBHOOK_SECRET>`
por los tuyos; usa el MISMO secreto que pusiste en Vercel):

```bash
curl -s "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  --data-urlencode "url=https://<tu-proyecto>.vercel.app/api/webhook" \
  --data-urlencode "secret_token=<WEBHOOK_SECRET>" \
  --data-urlencode 'allowed_updates=["message","edited_message"]'
```

Comprobar que quedo:
```bash
curl -s "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```
Debe mostrar tu `url` y `pending_update_count`.

> **No corras `poll.py` ni `run_polling.py` mientras uses webhook:** getUpdates y
> webhook son excluyentes (el webhook queda deshabilitado si algo llama getUpdates).

## 4. Probar

Manda `/ayuda` o `/trafico` al bot: debe responder al instante.
Si algo falla, revisa **Vercel → tu proyecto → Logs**.

---

## (Opcional) Memoria de viajes activos

Si quieres que `/viaje` recuerde tu ruta y el monitor te mande alertas:
conecta **Upstash Redis** (free tier, sin tarjeta) y reemplaza la escritura de
`state/*.json` por lectura/escritura en Redis. Pídelo y se integra.
