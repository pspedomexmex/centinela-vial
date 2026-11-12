# 🚛 Centinela Vial

**Bot de Telegram para monitoreo e inteligencia vial del transporte de carga en México.**
Registra una ruta y recibe alertas automáticas de incidentes, cierres, flujo vial,
clima severo y noticias de seguridad a lo largo del trayecto.

> **Arquitectura v3 — costo de operación: $0.** El bot responde al instante por
> **webhook serverless en Vercel** (plan Hobby gratis); el estado compartido vive
> en **Upstash Redis** (free tier, sin tarjeta) y las alertas automáticas se
> disparan cada 30 min con un **cron externo gratuito** (cron-job.org). Sin
> servidor 24/7, sin base de datos de pago.

---

## ✨ Qué hace

- **Monitoreo de ruta por usuario:** registras `origen → destino` y el bot vigila
  esa ruta cada 30 min, avisándote de incidentes nuevos.
- **Alertas en vivo:** incidentes y cierres (TomTom), flujo vial, clima severo
  (OpenMeteo), avisos oficiales (CAPUFE) y noticias viales.
- **Detección de reaperturas:** te avisa cuando una carretera cerrada vuelve a abrir.
- **Escaneos bajo demanda:** panorama vial nacional (`/escaneo`) y del corredor
  EdoMex→CDMX (`/zona`).
- **Noticias RCPN** (`/rcpn`): consulta en vivo de Google News (últimos 30 días).
- **Agente IA:** haz preguntas en lenguaje natural sobre tu ruta (Groq / Llama 3.x).

## 🧭 Comandos

| Comando | Qué hace |
|---|---|
| `/start`, `/ayuda` | Muestra la ayuda |
| `/viaje ORIGEN - DESTINO` | Inicia el monitoreo de una ruta. Ej: `/viaje CDMX - Monterrey` |
| `/alertas` | Incidentes en tu ruta **ahora** |
| `/ruta` | Desglose de tramos, km y tiempo |
| `/trafico` | Estado del tráfico de la ruta |
| `/estado` | Resumen del viaje activo |
| `/regiones` | Regiones/estados que cubre la ruta |
| `/detener` | Termina el monitoreo |
| `/escaneo` | Panorama vial nacional (tramos clave) |
| `/zona` | Corredor laboral ZMVM Norte (Neza, Ecatepec, Coacalco…) |
| `/rcpn` | Noticias de Resistencia Civil Pacífica Nacional (en vivo) |
| _(texto libre)_ | Pregunta al agente IA sobre tu ruta |

## 🏗 Arquitectura

```
                         ┌──────────── Vercel (serverless, gratis) ───────────┐
   comandos              │                                                    │
  Telegram ──POST──────► │  api/webhook.py → bot/dispatch.py → handlers        │
     ▲                   │                 → responde al instante              │
     │                   │                 → lee/escribe viajes en Redis       │
     │                   │                                                    │
     │  alertas          │  api/monitor.py  (protegido con MONITOR_SECRET)     │
     └───────────────────┤    └─ lee viajes de Redis → consulta fuentes        │
                         │       → alerta → de-dup en Redis                    │
                         └───────────┬───────────────────────┬────────────────┘
                                     │                        │
                      cada 30 min ◄──┘                        ▼
                   cron-job.org (gratis)            ┌──────────────────────┐
                   GET /api/monitor?secret=…        │  Upstash Redis        │
                                                    │  viajes · dedup ·     │
                                                    │  cierres (estado      │
                                                    │  compartido, 500K/mes)│
                                                    └──────────────────────┘

  Fuentes en vivo: TomTom · OpenMeteo · CAPUFE · Nitter · Google News · Google Maps · Groq
```

**Por qué webhook:** el bot responde al instante sin mantener un proceso 24/7. El
webhook valida el header secreto de Telegram, así solo Telegram puede invocarlo.

**Por qué Redis compartido:** el webhook (que atiende comandos) y el monitor (que
manda alertas) corren en invocaciones serverless distintas y efímeras. Necesitan
una memoria común donde el viaje que registras con `/viaje` quede guardado para que
el monitor lo lea después. Upstash Redis cumple eso gratis. El estado es diminuto
(unos pocos viajes + de-dup con expiración automática), así que **nunca se llena**
—a diferencia de la v1 con Supabase, que se pasó de los 500 MB acumulando el
dataset histórico de tesis, ya retirado.

> `db/store.py` tiene **doble backend**: usa Redis si hay credenciales de Upstash,
> y cae a archivos JSON locales si no (para desarrollo y la batería de tests).

## 🗂 Estructura

```
centinela-vial/
├─ api/                # funciones serverless de Vercel
│  ├─ webhook.py       # recibe comandos de Telegram y responde al instante
│  └─ monitor.py       # ciclo de alertas (lo dispara cron-job.org cada 30 min)
├─ bot/
│  ├─ dispatch.py      # enruta cada comando a su handler
│  ├─ handlers.py      # lógica de los comandos
│  ├─ agent.py         # agente IA (Groq)
│  ├─ poll.py          # (alternativa) sondeo por lotes — no se usa con webhook
│  └─ run_polling.py   # (alternativa) listener 24/7 para VM — no se usa con webhook
├─ monitor/
│  └─ run.py           # run_monitor(): revisa rutas y manda alertas
├─ db/
│  └─ store.py         # persistencia doble backend: Upstash Redis o JSON local
├─ regions/            # grafo de ciudades, regiones y parser de rutas
├─ sources/            # integraciones con fuentes de datos
├─ deploy/             # VERCEL.md (webhook + Redis + cron) y opción VM
├─ vercel.json         # config de las funciones serverless
├─ requirements.txt
├─ .env.example
├─ MANUAL.md           # manual de uso para operadores
└─ test_centinela_vial.py / test_store.py
```

## 🧱 Stack

- **Python 3.11**
- `python-telegram-bot`, `httpx`, `requests`, `googlemaps`, `groq`
- **Vercel** (webhook + endpoint de monitoreo serverless) — sin servidor 24/7
- **Upstash Redis** como estado compartido (free tier) · **cron-job.org** como reloj

## ⚙️ Instalación local (para desarrollo/pruebas)

```bash
git clone https://github.com/pspedomexmex/centinela-vial.git
cd centinela-vial

python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # rellena tus valores SOLO en local (no lo commitees)
python -m pytest -q                # correr la batería de tests
```

## 🔑 Variables de entorno

| Variable | Obligatoria | Para qué |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | Token del bot (de @BotFather) |
| `TOMTOM_KEY` | ✅ | Incidentes y flujo vial (TomTom) |
| `GMAPS_KEY` | ⬜ | Ruta y tráfico (Google Maps) |
| `GROQ_API_KEY` | ⬜ | Agente IA en lenguaje natural |
| `TWITTER_BEARER_TOKEN` | ⬜ | Avisos viales de X/Twitter |

Los nombres (sin valores) están en [`.env.example`](.env.example).

## 🚀 Despliegue (gratis, sin tarjeta)

La guía completa y detallada está en **[`deploy/VERCEL.md`](deploy/VERCEL.md)**. En resumen:

1. **Vercel:** importa el repo y despliega (detecta `api/*.py` solo). En *Settings
   → Environment Variables* pon `TELEGRAM_BOT_TOKEN`, `WEBHOOK_SECRET`, `TOMTOM_KEY`
   y los opcionales (`GMAPS_KEY`, `GROQ_API_KEY`, …).
2. **Webhook de Telegram:** regístralo apuntando a `…/api/webhook` con tu
   `WEBHOOK_SECRET` (comando `setWebhook` en la guía). El bot ya responde al instante.
3. **Upstash Redis:** crea una base gratis, copia `UPSTASH_REDIS_REST_URL` y
   `UPSTASH_REDIS_REST_TOKEN` a las variables de Vercel. Ahora `/viaje` recuerda tu ruta.
4. **cron-job.org:** crea un cronjob cada 30 min a
   `…/api/monitor?secret=<MONITOR_SECRET>` (mismo `MONITOR_SECRET` que pusiste en
   Vercel). Esto dispara las alertas automáticas.

> ⏱ **Latencia esperada:** los comandos responden **al instante** (webhook). Las
> alertas automáticas de ruta llegan cada 30 min (o la frecuencia que fijes en
> cron-job.org, hasta cada minuto).
>
> 🖥 **¿Prefieres una sola máquina?** `deploy/README.md` explica la alternativa de
> correr todo en una VM Always-Free (long-polling + cron del sistema), sin Vercel
> ni Redis externo. Elige una u otra, no ambas (chocan en Telegram).

## 🔐 Consideraciones de seguridad y uso ético/educativo

**Seguridad**
- **Ningún secreto en el código.** Todo se lee por `os.getenv()` y en producción
  vive en las **Environment Variables de Vercel**, nunca en el repositorio.
- El historial del proyecto se auditó: sin tokens ni credenciales filtradas.
- `.env` está en `.gitignore`; sólo se versiona `.env.example` (sin valores).
- **Webhook autenticado:** `api/webhook.py` valida el header secreto de Telegram
  (`X-Telegram-Bot-Api-Secret-Token`); rechaza con 401 cualquier POST que no venga
  de Telegram.
- **Endpoint de monitoreo protegido:** `api/monitor.py` exige `MONITOR_SECRET`; sin
  él responde 401, para que nadie más pueda dispararlo y agotar tu cuota de TomTom.
- El token de Upstash viaja solo en la cabecera `Authorization` sobre HTTPS.
- Si clonas o reutilizas este proyecto, **rota cualquier token** antes de publicarlo.

**Uso ético/educativo**
- Este proyecto es de carácter **educativo y de investigación** (apoyo a la
  operación de transporte y a estudios de seguridad vial).
- Sólo consume **información pública** de tráfico, clima y noticias. **No** almacena
  ni debe almacenarse información sensible (placas, rutas comerciales, clientes,
  datos personales de operadores).
- El módulo `/rcpn` agrega noticias de terceros y **muestra siempre un aviso** de
  que el contenido puede estar sesgado o ser incorrecto, recomendando verificar la
  fuente original antes de difundir.
- Respeta los **términos de servicio** de cada API/fuente (TomTom, Google, etc.) y
  sus límites de uso gratuito.

---

## 📜 Licencia

Proyecto educativo. Úsalo y adáptalo con responsabilidad, citando las fuentes de
datos y respetando sus términos.
