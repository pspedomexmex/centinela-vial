# Despliegue del bot por Webhook en Vercel (gratis, sin tarjeta)

El bot de comandos corre como una **funcion serverless** (`api/webhook.py`).
Telegram hace POST de cada mensaje a esa URL y el bot responde al instante.
No hay proceso encendido ni cron: perfecto para el plan **Hobby** (gratis).

El bot responde comandos **al instante** (webhook). Las alertas automáticas de ruta
las despacha el endpoint `/api/monitor`, que un cron externo llama cada 30 min. El
estado compartido (viajes activos, de-dup de alertas) vive en **Upstash Redis**;
sin él, los comandos de viaje y las alertas no funcionan en producción.

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

## 5. Memoria de viajes + alertas automáticas (Upstash Redis + cron-job.org)

Esto hace que `/viaje` **recuerde** tu ruta y que el monitor te mande alertas
cada 30 min. Todo gratis, sin tarjeta.

### 5.1 Crear la base Redis (Upstash)

1. Entra a **https://console.upstash.com** y regístrate (sin tarjeta).
2. **Redis → Create database** (elige una región cercana, p. ej. `us-east-1`).
3. En la base creada, abre la pestaña **REST API** y copia:
   - **UPSTASH_REDIS_REST_URL**
   - **UPSTASH_REDIS_REST_TOKEN**

> Free tier: 500K comandos/mes y 250 MB — de sobra para los viajes del bot.

### 5.2 Añadir las variables en Vercel

Vercel → tu proyecto → **Settings → Environment Variables** (marca *Production*):

| Nombre | Valor |
|---|---|
| `UPSTASH_REDIS_REST_URL` | el que copiaste de Upstash |
| `UPSTASH_REDIS_REST_TOKEN` | el que copiaste de Upstash |
| `MONITOR_SECRET` | una cadena aleatoria (`openssl rand -hex 16`) |

Vuelve a desplegar (**Deployments → Redeploy**) para que tomen efecto. Desde
ahora `/viaje`, `/estado` y `/detener` **sí** recuerdan tu ruta (ya no es /tmp
efímero): el estado vive en Redis.

### 5.3 Programar las alertas cada 30 min (cron-job.org)

El plan gratis de Vercel solo permite cron **1 vez al día**, así que usamos un
programador externo gratuito:

1. Entra a **https://cron-job.org** y regístrate (gratis).
2. **Create cronjob**:
   - **URL:** `https://<tu-proyecto>.vercel.app/api/monitor?secret=<MONITOR_SECRET>`
     (el mismo `MONITOR_SECRET` que pusiste en Vercel)
   - **Schedule:** cada **30 minutos** (o lo que prefieras; cron-job.org permite
     hasta cada minuto).
3. Guarda. A partir de ahí, cada 30 min cron-job.org llama a tu endpoint, que
   lee los viajes activos de Redis y manda las alertas nuevas a Telegram.

> **Seguridad:** el endpoint `api/monitor.py` rechaza con **401** cualquier
> petición sin el `MONITOR_SECRET` correcto. Así nadie más puede dispararlo ni
> agotar tu cuota de TomTom. Puedes probarlo abriendo la URL sin el secreto
> (debe responder "no autorizado") y luego con el secreto (debe ejecutar).

### 5.4 Comprobar

- Manda `/viaje CDMX - Monterrey` al bot → debe confirmar el viaje.
- Manda `/estado` → debe seguir recordando tu viaje (prueba de que Redis funciona).
- Espera un ciclo (o abre la URL del monitor con el secreto) → si hay incidentes
  nuevos en tu ruta, llegan a Telegram.
