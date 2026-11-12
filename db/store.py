"""
Centinela Vial — Capa de persistencia con DOBLE backend (Upstash Redis o JSON).

Expone una única interfaz (guardar_viaje, get_viaje, ya_enviada, …) y elige el
almacén automáticamente según el entorno:

  • Upstash Redis (producción serverless):
      Si están definidas UPSTASH_REDIS_REST_URL y UPSTASH_REDIS_REST_TOKEN, el
      estado vive en Redis a través de su API REST (una simple petición HTTPS por
      comando — ideal para funciones serverless como el webhook de Vercel, que no
      pueden mantener conexiones persistentes). Este es el almacén COMPARTIDO que
      permite que el webhook (Vercel) y el monitor de alertas lean y escriban los
      mismos viajes. Free tier: 500K comandos/mes, 250 MB, sin tarjeta.

  • JSON en disco (desarrollo local y tests):
      Si no hay credenciales de Redis, cae a archivos JSON bajo STATE_DIR (./state).
      Útil para correr los tests y probar en local sin depender de la nube.

Qué se guarda (diminuto): viaje activo por chat, de-dup de alertas y cierres
activos. NO se guarda ningún histórico.

Seguridad:
  - Las credenciales de Redis se leen SIEMPRE de variables de entorno.
  - El token de Upstash viaja solo en la cabecera Authorization sobre HTTPS.
  - Ningún secreto se escribe en disco ni en logs.
"""
from __future__ import annotations

import os
import json
import time
import tempfile
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

# ── Selección de backend ──────────────────────────────────────────────────────
_REDIS_URL   = os.environ.get("UPSTASH_REDIS_REST_URL", "").rstrip("/")
_REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
_USE_REDIS   = bool(_REDIS_URL and _REDIS_TOKEN)

# Zona horaria de México (UTC-6) para sellos de tiempo legibles.
_TZ_MX = timezone(timedelta(hours=-6))

# Ventana de de-dup: no re-alertar el mismo incidente antes de N horas.
_DEDUP_TTL_SEG = 6 * 3600


def backend_actual() -> str:
    """Devuelve 'redis' o 'json' — útil para health checks y logs."""
    return "redis" if _USE_REDIS else "json"


def _ahora_iso() -> str:
    """Sello de tiempo actual en ISO-8601 con zona horaria de México."""
    return datetime.now(_TZ_MX).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
#  BACKEND REDIS (Upstash REST API)
# ══════════════════════════════════════════════════════════════════════════════
# La REST API de Upstash recibe un comando Redis como arreglo JSON, por ejemplo
# ["SET", "clave", "valor"], y responde {"result": ...}. Un pipeline (varios
# comandos en una sola petición) se envía como arreglo de arreglos a /pipeline.

def _redis_cmd(*args) -> object:
    """Ejecuta un comando Redis vía REST y devuelve su 'result'."""
    import httpx  # import diferido: solo se necesita en modo Redis
    r = httpx.post(
        _REDIS_URL,
        headers={"Authorization": f"Bearer {_REDIS_TOKEN}"},
        json=[str(a) for a in args],
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json().get("result")


# ── Claves Redis ──────────────────────────────────────────────────────────────
#   viajes                  → hash  { chat_id: json_del_viaje }
#   cierres:<chat_id>       → hash  { hash_cierre: descripcion }
#   dedup:<chat_id>:<hash>  → string con TTL (expira solo tras _DEDUP_TTL_SEG)

def _r_guardar_viaje(chat_id: int, viaje: dict) -> None:
    _redis_cmd("HSET", "viajes", chat_id, json.dumps(viaje, ensure_ascii=False))
    _redis_cmd("DEL", f"cierres:{chat_id}")  # limpiar cierres del viaje anterior


def _r_get_viaje(chat_id: int) -> dict | None:
    raw = _redis_cmd("HGET", "viajes", chat_id)
    if not raw:
        return None
    v = json.loads(raw)
    return v if v.get("activo", True) else None


def _r_get_viajes_activos() -> list[dict]:
    plano = _redis_cmd("HGETALL", "viajes") or []
    # HGETALL devuelve [field1, val1, field2, val2, ...]
    viajes = []
    for i in range(1, len(plano), 2):
        try:
            v = json.loads(plano[i])
            if v.get("activo", True):
                viajes.append(v)
        except (json.JSONDecodeError, TypeError):
            continue
    return viajes


def _r_detener_viaje(chat_id: int) -> None:
    _redis_cmd("HDEL", "viajes", chat_id)
    _redis_cmd("DEL", f"cierres:{chat_id}")


def _r_ya_enviada(chat_id: int, hash_alerta: str) -> bool:
    return bool(_redis_cmd("EXISTS", f"dedup:{chat_id}:{hash_alerta}"))


def _r_marcar_enviada(chat_id: int, hash_alerta: str) -> None:
    # SET con expiración: Redis purga el registro solo tras la ventana de de-dup.
    _redis_cmd("SET", f"dedup:{chat_id}:{hash_alerta}", _ahora_iso(),
               "EX", _DEDUP_TTL_SEG)


def _r_get_cierres_activos(chat_id: int) -> dict[str, str]:
    plano = _redis_cmd("HGETALL", f"cierres:{chat_id}") or []
    return {plano[i]: plano[i + 1] for i in range(0, len(plano), 2)}


def _r_actualizar_cierres(chat_id: int, cierres_actuales: dict[str, str]) -> list[str]:
    previos = _r_get_cierres_activos(chat_id)
    reabiertos_desc = [d for h, d in previos.items() if h not in cierres_actuales]
    # Reemplazar el conjunto de cierres por el actual.
    _redis_cmd("DEL", f"cierres:{chat_id}")
    if cierres_actuales:
        args = ["HSET", f"cierres:{chat_id}"]
        for h, desc in cierres_actuales.items():
            args += [h, desc]
        _redis_cmd(*args)
    return reabiertos_desc


def _r_limpiar_cierres_viaje(chat_id: int) -> None:
    _redis_cmd("DEL", f"cierres:{chat_id}")


# ══════════════════════════════════════════════════════════════════════════════
#  BACKEND JSON (archivos en disco — desarrollo y tests)
# ══════════════════════════════════════════════════════════════════════════════
STATE_DIR     = os.environ.get("STATE_DIR", "state")
_VIAJES_FILE  = "viajes.json"
_ALERTAS_FILE = "alertas.json"
_CIERRES_FILE = "cierres.json"

try:
    import fcntl  # Linux/macOS
    _HAS_FCNTL = True
except ImportError:  # pragma: no cover
    _HAS_FCNTL = False


def _path(nombre: str) -> str:
    return os.path.join(STATE_DIR, nombre)


def _asegurar_dir() -> None:
    os.makedirs(STATE_DIR, exist_ok=True)


@contextmanager
def _lock(nombre: str):
    """Bloqueo exclusivo por archivo para serializar escrituras locales."""
    _asegurar_dir()
    f = open(_path(nombre + ".lock"), "w")
    try:
        if _HAS_FCNTL:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if _HAS_FCNTL:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


def _load(nombre: str) -> dict:
    ruta = _path(nombre)
    if not os.path.exists(ruta):
        return {}
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save(nombre: str, data: dict) -> None:
    """Escritura atómica: archivo temporal + os.replace."""
    _asegurar_dir()
    ruta = _path(nombre)
    fd, tmp = tempfile.mkstemp(dir=STATE_DIR, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ruta)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _j_guardar_viaje(chat_id: int, viaje: dict) -> None:
    with _lock(_VIAJES_FILE):
        viajes = _load(_VIAJES_FILE)
        viajes[str(chat_id)] = viaje
        _save(_VIAJES_FILE, viajes)
    _j_limpiar_cierres_viaje(chat_id)


def _j_get_viaje(chat_id: int) -> dict | None:
    v = _load(_VIAJES_FILE).get(str(chat_id))
    if not v or not v.get("activo", True):
        return None
    return v


def _j_get_viajes_activos() -> list[dict]:
    return [v for v in _load(_VIAJES_FILE).values() if v.get("activo", True)]


def _j_detener_viaje(chat_id: int) -> None:
    with _lock(_VIAJES_FILE):
        viajes = _load(_VIAJES_FILE)
        if str(chat_id) in viajes:
            del viajes[str(chat_id)]
            _save(_VIAJES_FILE, viajes)


def _j_ya_enviada(chat_id: int, hash_alerta: str) -> bool:
    return hash_alerta in _load(_ALERTAS_FILE).get(str(chat_id), {})


def _j_marcar_enviada(chat_id: int, hash_alerta: str) -> None:
    with _lock(_ALERTAS_FILE):
        alertas = _load(_ALERTAS_FILE)
        alertas.setdefault(str(chat_id), {})[hash_alerta] = _ahora_iso()
        _save(_ALERTAS_FILE, alertas)


def _j_limpiar_alertas_viejas(horas: int) -> None:
    cutoff = datetime.now(_TZ_MX) - timedelta(hours=horas)
    with _lock(_ALERTAS_FILE):
        alertas = _load(_ALERTAS_FILE)
        cambiado = False
        for chat_id, hashes in list(alertas.items()):
            vigentes = {}
            for h, ts in hashes.items():
                try:
                    if datetime.fromisoformat(ts) >= cutoff:
                        vigentes[h] = ts
                    else:
                        cambiado = True
                except (ValueError, TypeError):
                    cambiado = True
            if vigentes:
                alertas[chat_id] = vigentes
            else:
                del alertas[chat_id]
                cambiado = True
        if cambiado:
            _save(_ALERTAS_FILE, alertas)


def _j_get_cierres_activos(chat_id: int) -> dict[str, str]:
    return dict(_load(_CIERRES_FILE).get(str(chat_id), {}))


def _j_actualizar_cierres(chat_id: int, cierres_actuales: dict[str, str]) -> list[str]:
    with _lock(_CIERRES_FILE):
        cierres = _load(_CIERRES_FILE)
        previos = dict(cierres.get(str(chat_id), {}))
        reabiertos_desc = [d for h, d in previos.items() if h not in cierres_actuales]
        if cierres_actuales:
            cierres[str(chat_id)] = dict(cierres_actuales)
        else:
            cierres.pop(str(chat_id), None)
        _save(_CIERRES_FILE, cierres)
    return reabiertos_desc


def _j_limpiar_cierres_viaje(chat_id: int) -> None:
    with _lock(_CIERRES_FILE):
        cierres = _load(_CIERRES_FILE)
        if str(chat_id) in cierres:
            del cierres[str(chat_id)]
            _save(_CIERRES_FILE, cierres)


# ══════════════════════════════════════════════════════════════════════════════
#  INTERFAZ PÚBLICA (despacha al backend activo)
# ══════════════════════════════════════════════════════════════════════════════

def guardar_viaje(chat_id: int, datos: dict) -> None:
    """Crea o reemplaza el viaje activo de un chat."""
    viaje = {
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
    if _USE_REDIS:
        _r_guardar_viaje(chat_id, viaje)
    else:
        _j_guardar_viaje(chat_id, viaje)


def get_viaje(chat_id: int) -> dict | None:
    """Devuelve el viaje activo del chat, o None."""
    return _r_get_viaje(chat_id) if _USE_REDIS else _j_get_viaje(chat_id)


def get_viajes_activos() -> list[dict]:
    """Lista todos los viajes activos (los que usa el monitor)."""
    return _r_get_viajes_activos() if _USE_REDIS else _j_get_viajes_activos()


def detener_viaje(chat_id: int) -> None:
    """Elimina el viaje activo del chat."""
    if _USE_REDIS:
        _r_detener_viaje(chat_id)
    else:
        _j_detener_viaje(chat_id)


def ya_enviada(chat_id: int, hash_alerta: str) -> bool:
    """True si esa alerta ya fue enviada a ese chat."""
    return _r_ya_enviada(chat_id, hash_alerta) if _USE_REDIS else _j_ya_enviada(chat_id, hash_alerta)


def marcar_enviada(chat_id: int, hash_alerta: str) -> None:
    """Registra una alerta como enviada."""
    if _USE_REDIS:
        _r_marcar_enviada(chat_id, hash_alerta)
    else:
        _j_marcar_enviada(chat_id, hash_alerta)


def limpiar_alertas_viejas(horas: int = 6) -> None:
    """
    Purga de-dups vencidos. En Redis es un no-op: cada registro expira solo
    gracias a su TTL. En JSON se recorre y limpia manualmente.
    """
    if _USE_REDIS:
        return
    _j_limpiar_alertas_viejas(horas)


def get_cierres_activos(chat_id: int) -> dict[str, str]:
    """Devuelve {hash_cierre: descripcion} de los cierres vigentes del chat."""
    return _r_get_cierres_activos(chat_id) if _USE_REDIS else _j_get_cierres_activos(chat_id)


def actualizar_cierres(chat_id: int, cierres_actuales: dict[str, str]) -> list[str]:
    """Sincroniza cierres y devuelve las descripciones de los que se reabrieron."""
    if _USE_REDIS:
        return _r_actualizar_cierres(chat_id, cierres_actuales)
    return _j_actualizar_cierres(chat_id, cierres_actuales)


def limpiar_cierres_viaje(chat_id: int) -> None:
    """Elimina todos los cierres activos de un chat."""
    if _USE_REDIS:
        _r_limpiar_cierres_viaje(chat_id)
    else:
        _j_limpiar_cierres_viaje(chat_id)
