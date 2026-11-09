# 🚛 Centinela Vial

**Bot de Telegram para monitoreo e inteligencia vial del transporte de carga en México.**
Registra una ruta y recibe alertas automáticas de incidentes, cierres, flujo vial,
clima severo y noticias de seguridad a lo largo del trayecto.

> **Arquitectura v2 — costo de operación: $0.** Sin servidor, sin base de datos de
> pago. Todo corre en **GitHub Actions** (gratis en repositorios públicos) y el
> estado se guarda en **archivos JSON versionados** dentro del propio repositorio.

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
                    ┌─────────────── GitHub (repositorio público) ────────────────┐
                    │                                                              │
  Telegram ◄────────┤  Workflow bot.yml       (cron cada 5 min)                    │
     ▲              │    └─ bot/poll.py  → getUpdates → bot/dispatch.py            │
     │  comandos    │                     → handlers → responde                    │
     │              │                     → actualiza state/*.json                 │
     │              │                                                              │
     └──── alertas ─┤  Workflow monitor.yml   (cron cada 30 min)                   │
          push      │    └─ monitor/run.py → lee viajes → consulta fuentes         │
                    │                      → alerta → de-dup en state/*.json        │
                    │                                                              │
                    │  Estado versionado:                                          │
                    │    state/viajes.json · state/alertas.json ·                  │
                    │    state/cierres.json · state/offset.json                    │
                    │    (los workflows commitean sólo si hubo cambios)            │
                    └──────────────────────────────────────────────────────────────┘

  Fuentes en vivo: TomTom · OpenMeteo · CAPUFE · Nitter · Google News · Google Maps · Groq
```

**Por qué sin servidor:** el bot no mantiene un proceso 24/7. Un workflow sondea
los comandos por lotes (`getUpdates`) cada 5 min y otro revisa las rutas cada 30 min.
Al no exponer ningún webhook público, **no hay endpoint entrante que atacar**.

**Por qué JSON versionado:** el estado operativo (viaje activo, de-dup de alertas,
cierres) es diminuto. Guardarlo en archivos del repo es gratis, auditable (ves el
diff de qué se alertó y cuándo) e imposible de "llenar y cobrar" como una base de
pago. La versión anterior usaba Supabase y dejó de ser gratuita al rebasar los 500 MB
acumulando un dataset histórico que **ya no forma parte de este proyecto**.

## 🗂 Estructura

```
centinela-vial/
├─ bot/
│  ├─ poll.py          # sondeo de comandos (getUpdates) — entrypoint de bot.yml
│  ├─ dispatch.py      # enruta cada comando a su handler
│  ├─ handlers.py      # lógica de los comandos
│  └─ agent.py         # agente IA (Groq)
├─ monitor/
│  └─ run.py           # monitoreo de rutas y alertas — entrypoint de monitor.yml
├─ db/
│  └─ store.py         # persistencia JSON (viajes, de-dup, cierres)
├─ regions/            # grafo de ciudades, regiones y parser de rutas
├─ sources/            # integraciones con fuentes de datos
├─ state/              # estado operativo en JSON (versionado)
├─ .github/workflows/
│  ├─ bot.yml          # cron cada 5 min
│  └─ monitor.yml      # cron cada 30 min
├─ requirements.txt
├─ .env.example
├─ MANUAL.md           # manual de uso para operadores
└─ test_centinela_vial.py / test_store.py
```

## 🧱 Stack

- **Python 3.11**
- `python-telegram-bot`, `httpx`, `requests`, `googlemaps`, `groq`
- **GitHub Actions** como orquestador (cron) — sin servidor
- Persistencia en **JSON versionado**

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

## 🚀 Despliegue en GitHub Actions (gratis)

1. **Haz el repositorio público** (Actions es ilimitado y gratis en repos públicos;
   en privados hay un tope de 2000 min/mes). El código no contiene secretos.
2. **Carga los secretos** en *Settings → Secrets and variables → Actions →
   New repository secret*: `TELEGRAM_BOT_TOKEN`, `TOMTOM_KEY` y los opcionales que uses.
3. **Permite que los workflows escriban** el estado: *Settings → Actions → General →
   Workflow permissions → **Read and write permissions***.
4. **Activa los workflows:** se disparan solos por cron, o manualmente desde la
   pestaña *Actions → Run workflow* (`workflow_dispatch`).
5. Escribe `/start` a tu bot en Telegram. En el próximo ciclo de sondeo (≤5 min)
   responderá.

> ⏱ **Latencia esperada:** los comandos responden en ≤5 min (sondeo) y las alertas
> de ruta llegan cada 30 min. Los crons de GitHub Actions pueden retrasarse algunos
> minutos en horas de alta demanda; es normal.

## 🔐 Consideraciones de seguridad y uso ético/educativo

**Seguridad**
- **Ningún secreto en el código.** Todo se lee por `os.getenv()` y en producción
  vive en **GitHub Secrets**, nunca en los archivos YAML ni en el repositorio.
- El historial del proyecto se auditó: sin tokens ni credenciales filtradas.
- `.env` está en `.gitignore`; sólo se versiona `.env.example` (sin valores).
- El bot usa **sondeo saliente** (`getUpdates`), no un webhook: **no expone ningún
  endpoint público**, reduciendo la superficie de ataque.
- Los workflows corren con **permisos mínimos** (`contents: write`, sólo para
  commitear el estado).
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
