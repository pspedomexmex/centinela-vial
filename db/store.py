"""
Centinela Vial — Capa de persistencia ligera en archivos JSON versionados.

Reemplaza a db/supabase_client.py. En la arquitectura v2 (100% GitHub Actions,
costo $0) el estado NO vive en una base de datos externa de pago, sino en
archivos JSON que los propios workflows leen, escriben y commitean al repo.

Qué se guarda (y SÓLO esto — es diminuto, unas pocas filas):
  - viajes.json   : viaje activo por chat de Telegram (qué ruta vigilar).
  - alertas.json  : de-duplicación de alertas ya enviadas (no re-spamear).
  - cierres.json  : cierres de carretera activos por chat (detectar reaperturas).

NO se guarda ningún histórico (clima/flujo/incidentes acumulados): ese era el
dataset de tesis que llenó los 500 MB de Supabase y fue eliminado a propósito.

Decisiones de diseño por seguridad y robustez:
  - Escritura ATÓMICA (archivo temporal + os.replace) para no corromper el JSON
    si el proceso muere a la mitad de un guardado.
  - Bloqueo de archivo (fcntl) para serializar escrituras concurrentes dentro
    de un mismo runner (p. ej. varias corrutinas asyncio).
  - La ruta del estado es configurable por STATE_DIR; por defecto ./state.
  - Ningún secreto se maneja aquí: este módulo sólo toca archivos locales.

Nota sobre concurrencia ENTRE workflows (bot.yml vs monitor.yml): como corren en
runners distintos, el bloqueo local no basta. Esa carrera se evita a nivel de
GitHub Actions con un grupo `concurrency` compartido + git rebase antes de push
(ver los workflows). Aquí garantizamos la integridad de cada escritura local.
"""
from __future__ import annotations

import os
import json
import time
import tempfile
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

try:
    import fcntl  # disponible en Linux (runners de GitHub Actions) y macOS
    _HAS_FCNTL = True
except ImportError:  # pragma: no cover — Windows no tiene fcntl
    _HAS_FCNTL = False

# ── Configuración de rutas ────────────────────────────────────────────────────
# STATE_DIR permite redirigir el estado en tests o entornos distintos.
STATE_DIR = os.environ.get("STATE_DIR", "state")

_VIAJES_FILE  = "viajes.json"
_ALERTAS_FILE = "alertas.json"
_CIERRES_FILE = "cierres.json"

# Zona horaria de México (UTC-6) para sellos de tiempo legibles.
_TZ_MX = timezone(timedelta(hours=-6))


# ── Utilidades internas de E/S ────────────────────────────────────────────────

def _path(nombre: str) -> str:
    """Ruta absoluta de un archivo de estado dentro de STATE_DIR."""
    return os.path.join(STATE_DIR, nombre)


def _asegurar_dir() -> None:
    """Crea el directorio de estado si no existe."""
    os.makedirs(STATE_DIR, exist_ok=True)


@contextmanager
def _lock(nombre: str):
    """
    Bloqueo exclusivo basado en un archivo .lock adyacente.
    Serializa escrituras concurrentes dentro del mismo proceso/runner.
    En plataformas sin fcntl degrada a no-op (no rompe, sólo no bloquea).
    """
    _asegurar_dir()
    lock_path = _path(nombre + ".lock")
    f = open(lock_path, "w")
    try:
        if _HAS_FCNTL:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if _HAS_FCNTL:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


def _load(nombre: str) -> dict:
    """Lee un archivo de estado JSON. Si no existe o está corrupto, devuelve {}."""
    ruta = _path(nombre)
    if not os.path.exists(ruta):
        return {}
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            data = json.load(f)
            # El estado siempre es un objeto (dict); un tipo inesperado se descarta.
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        # Ante corrupción preferimos continuar con estado vacío a tumbar el bot.
        return {}


def _save(nombre: str, data: dict) -> None:
    """
    Escribe un archivo de estado de forma ATÓMICA:
    primero a un archivo temporal en el mismo directorio y luego os.replace,
    que es atómico en el mismo sistema de archivos. Así nunca queda un JSON
    a medio escribir si el proceso se interrumpe.
    """
    _asegurar_dir()
    ruta = _path(nombre)
    # delete=False porque movemos el archivo nosotros con os.replace.
    fd, tmp = tempfile.mkstemp(dir=STATE_DIR, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())  # garantizar que los bytes llegan al disco
        os.replace(tmp, ruta)     # intercambio atómico
    except Exception:
        # Si algo falla, limpiamos el temporal para no dejar basura.
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _ahora_iso() -> str:
    """Sello de tiempo actual en ISO-8601 con zona horaria de México."""
    return datetime.now(_TZ_MX).isoformat()


# ── Viajes activos ────────────────────────────────────────────────────────────
# Esquema en viajes.json:  { "<chat_id>": { ...datos del viaje... }, ... }
# Las claves JSON son strings; convertimos a int al exponer chat_id.

def guardar_viaje(chat_id: int, datos: dict) -> None:
    """
    Crea o reemplaza el viaje activo de un chat.
    Al iniciar un viaje nuevo se limpian los cierres previos de ese chat para
    no reportar falsas 'reaperturas' de cierres de un viaje anterior.
    """
    with _lock(_VIAJES_FILE):
        viajes = _load(_VIAJES_FILE)
        viajes[str(chat_id)] = {
            "chat_id":      chat_id,
            "origen":       datos["origen"],
            "destino":      datos["destino"],
            "origen_fmt":   datos.get("origen_fmt", ""),
            "destino_fmt":  datos.get("destino_fmt", ""),
            "regiones":     datos.get("regiones", []),
            "estados":      datos.get("estados", []),
            "distancia_km": datos.get("distancia_km"),
            "duracion_hrs": datos.get("duracion_hrs"),
            "city_path":    datos.get("city_path"),
            "activo":       True,
            "creado_en":    _ahora_iso(),
        }
        _save(_VIAJES_FILE, viajes)

    # Limpieza de cierres del viaje anterior (equivale al delete de Supabase).
    limpiar_cierres_viaje(chat_id)


def get_viaje(chat_id: int) -> dict | None:
    """Devuelve el viaje activo del chat, o None si no tiene."""
    viajes = _load(_VIAJES_FILE)
    v = viajes.get(str(chat_id))
    if not v or not v.get("activo", True):
        return None
    return v


def get_viajes_activos() -> list[dict]:
    """Lista todos los viajes activos (los que usa el monitor por cron)."""
    viajes = _load(_VIAJES_FILE)
    return [v for v in viajes.values() if v.get("activo", True)]


def detener_viaje(chat_id: int) -> None:
    """Elimina el viaje activo del chat (termina el monitoreo)."""
    with _lock(_VIAJES_FILE):
        viajes = _load(_VIAJES_FILE)
        if str(chat_id) in viajes:
            del viajes[str(chat_id)]
            _save(_VIAJES_FILE, viajes)


# ── De-duplicación de alertas ─────────────────────────────────────────────────
# Esquema en alertas.json:  { "<chat_id>": { "<hash_alerta>": "<iso_timestamp>" } }

def ya_enviada(chat_id: int, hash_alerta: str) -> bool:
    """True si esa alerta ya fue enviada a ese chat (evita re-alertar)."""
    alertas = _load(_ALERTAS_FILE)
    return hash_alerta in alertas.get(str(chat_id), {})


def marcar_enviada(chat_id: int, hash_alerta: str) -> None:
    """Registra una alerta como enviada, con su marca de tiempo."""
    with _lock(_ALERTAS_FILE):
        alertas = _load(_ALERTAS_FILE)
        alertas.setdefault(str(chat_id), {})[hash_alerta] = _ahora_iso()
        _save(_ALERTAS_FILE, alertas)


def limpiar_alertas_viejas(horas: int = 6) -> None:
    """
    Elimina registros de alertas enviadas hace más de `horas`, para permitir
    re-alertar un incidente que reaparezca pasado ese tiempo. Mantiene el
    archivo pequeño.
    """
    cutoff = datetime.now(_TZ_MX) - timedelta(hours=horas)
    with _lock(_ALERTAS_FILE):
        alertas = _load(_ALERTAS_FILE)
        cambiado = False
        for chat_id, hashes in list(alertas.items()):
            vigentes = {}
            for h, ts in hashes.items():
                try:
                    cuando = datetime.fromisoformat(ts)
                except (ValueError, TypeError):
                    # Marca de tiempo ilegible: la descartamos por seguridad.
                    cambiado = True
                    continue
                if cuando >= cutoff:
                    vigentes[h] = ts
                else:
                    cambiado = True
            if vigentes:
                alertas[chat_id] = vigentes
            else:
                del alertas[chat_id]
                cambiado = True
        if cambiado:
            _save(_ALERTAS_FILE, alertas)


# ── Cierres de carretera activos (detección de reaperturas) ───────────────────
# Esquema en cierres.json:  { "<chat_id>": { "<hash_cierre>": "<descripcion>" } }

def get_cierres_activos(chat_id: int) -> dict[str, str]:
    """Devuelve {hash_cierre: descripcion} de los cierres vigentes del chat."""
    cierres = _load(_CIERRES_FILE)
    return dict(cierres.get(str(chat_id), {}))


def actualizar_cierres(chat_id: int, cierres_actuales: dict[str, str]) -> list[str]:
    """
    Sincroniza los cierres activos con el estado actual de las fuentes.
      - Cierres nuevos: se registran.
      - Cierres que desaparecieron: se eliminan y se retornan sus descripciones
        (son las carreteras que se REABRIERON, para notificar al operador).
    Devuelve la lista de descripciones de cierres reabiertos.
    """
    with _lock(_CIERRES_FILE):
        cierres = _load(_CIERRES_FILE)
        previos = dict(cierres.get(str(chat_id), {}))

        # Reaperturas = estaban antes y ya no están.
        reabiertos_desc = [desc for h, desc in previos.items()
                           if h not in cierres_actuales]

        # El nuevo conjunto de cierres del chat es exactamente el actual.
        if cierres_actuales:
            cierres[str(chat_id)] = dict(cierres_actuales)
        else:
            cierres.pop(str(chat_id), None)

        _save(_CIERRES_FILE, cierres)

    return reabiertos_desc


def limpiar_cierres_viaje(chat_id: int) -> None:
    """Elimina todos los cierres activos de un chat (al detener o reiniciar viaje)."""
    with _lock(_CIERRES_FILE):
        cierres = _load(_CIERRES_FILE)
        if str(chat_id) in cierres:
            del cierres[str(chat_id)]
            _save(_CIERRES_FILE, cierres)
