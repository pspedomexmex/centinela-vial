# Despliegue del bot de comandos (listener persistente 24/7)

El **bot de comandos** (`/viaje`, `/trafico`, `/ruta`, …) necesita un proceso que
escuche **siempre**. GitHub Actions (cron) no sirve para eso: retrasa o descarta
las corridas programadas y cada corrida solo escucha unos segundos. Por eso el
bot se ejecuta aqui como **servicio permanente** (`systemd`) en una maquina
siempre encendida, por ejemplo una **VM Always-Free de Oracle Cloud** (gratis).

> El **monitor de alertas** (`monitor/run.py`) si vive bien en GitHub Actions
> (`monitor.yml`): es un trabajo periodico que solo **envia** mensajes. No usa
> `getUpdates`, asi que **no** choca con este listener.

---

## 1. Crear la VM (Oracle Cloud Always-Free)

1. En Oracle Cloud, crea una instancia **Always Free** (shape `VM.Standard.A1.Flex`
   Ampere, o `E2.1.Micro`), con **Ubuntu 22.04**.
2. Guarda la llave SSH y abre el acceso (la VM ya trae SSH).
3. Conectate:  `ssh ubuntu@IP_DE_TU_VM`

## 2. Preparar el entorno

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

git clone https://github.com/pspedomexmex/centinela-vial.git
cd centinela-vial

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 3. Configurar los secretos (NO se versionan)

```bash
cp .env.example .env
nano .env          # pega tus valores reales (TELEGRAM_BOT_TOKEN, TOMTOM_KEY, ...)
chmod 600 .env     # solo tu usuario puede leerlo
```

> Usa un token **rotado** (el viejo que estuvo en el historial ya no sirve).

## 4. Instalar el servicio systemd

```bash
# Copia la plantilla y AJUSTA las rutas/usuario si no usas /home/ubuntu:
sudo cp deploy/centinela-vial-bot.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now centinela-vial-bot

# Ver estado y logs en vivo:
systemctl status centinela-vial-bot
journalctl -u centinela-vial-bot -f
```

El servicio arranca solo al reiniciar la VM y se reinicia si se cae.

## 5. Apagar el cron del bot (evita el 409 Conflict)

Un token = **un solo** `getUpdates` a la vez. Si el workflow del bot siguiera
corriendo a la par de la VM, chocarian. Por eso `bot.yml` se elimino del repo.
Si lo ves aun habilitado en la pestaña **Actions**, desactivalo ahi.

El `poll.py` original queda como variante "por lotes" de referencia, pero **no
lo corras** mientras la VM tenga el listener activo.

---

## Comprobacion

Manda `/estado` o `/ayuda` al bot en Telegram: debe responder al instante.
Si no responde, revisa `journalctl -u centinela-vial-bot -f` para ver el error.
