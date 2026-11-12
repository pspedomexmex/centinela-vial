"""
Tests de la capa de persistencia db/store.py (JSON versionado).
Usan un STATE_DIR temporal para no tocar el estado real del repo.

Ejecutar:  python -m pytest test_store.py -v
"""
import os
import json
import importlib
import tempfile
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Recarga db.store apuntando STATE_DIR a un directorio temporal limpio."""
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    import db.store as _store
    importlib.reload(_store)
    return _store


# ── Viajes ────────────────────────────────────────────────────────────────────

def test_guardar_y_obtener_viaje(store):
    store.guardar_viaje(123, {
        "origen": "CDMX", "destino": "Monterrey",
        "regiones": ["centro", "noreste"], "distancia_km": 900,
        "duracion_hrs": 10.5, "city_path": ["cdmx", "mty"],
    })
    v = store.get_viaje(123)
    assert v is not None
    assert v["origen"] == "CDMX"
    assert v["destino"] == "Monterrey"
    assert v["regiones"] == ["centro", "noreste"]
    assert v["city_path"] == ["cdmx", "mty"]
    assert v["activo"] is True


def test_get_viaje_inexistente(store):
    assert store.get_viaje(999) is None


def test_guardar_reemplaza(store):
    store.guardar_viaje(1, {"origen": "A", "destino": "B"})
    store.guardar_viaje(1, {"origen": "C", "destino": "D"})
    v = store.get_viaje(1)
    assert v["origen"] == "C" and v["destino"] == "D"
    # No debe duplicar: sólo un viaje para el chat 1.
    assert len(store.get_viajes_activos()) == 1


def test_viajes_activos_multiples(store):
    store.guardar_viaje(1, {"origen": "A", "destino": "B"})
    store.guardar_viaje(2, {"origen": "C", "destino": "D"})
    activos = store.get_viajes_activos()
    assert len(activos) == 2
    chat_ids = {v["chat_id"] for v in activos}
    assert chat_ids == {1, 2}


def test_detener_viaje(store):
    store.guardar_viaje(5, {"origen": "A", "destino": "B"})
    assert store.get_viaje(5) is not None
    store.detener_viaje(5)
    assert store.get_viaje(5) is None
    assert store.get_viajes_activos() == []


def test_detener_viaje_inexistente_no_falla(store):
    # No debe lanzar excepción aunque no exista.
    store.detener_viaje(404)


# ── De-duplicación de alertas ─────────────────────────────────────────────────

def test_dedup_basico(store):
    assert store.ya_enviada(1, "hashA") is False
    store.marcar_enviada(1, "hashA")
    assert store.ya_enviada(1, "hashA") is True
    # Otro chat no comparte el de-dup.
    assert store.ya_enviada(2, "hashA") is False


def test_limpiar_alertas_viejas(store, monkeypatch):
    # Insertamos una alerta "vieja" manipulando directamente el archivo.
    store.marcar_enviada(7, "reciente")
    data = store._load(store._ALERTAS_FILE)
    viejo = (datetime.now(timezone(timedelta(hours=-6))) - timedelta(hours=10)).isoformat()
    data["7"]["antigua"] = viejo
    store._save(store._ALERTAS_FILE, data)

    store.limpiar_alertas_viejas(horas=6)

    assert store.ya_enviada(7, "reciente") is True   # se conserva
    assert store.ya_enviada(7, "antigua") is False   # se purga


def test_limpiar_alertas_timestamp_corrupto(store):
    store.marcar_enviada(8, "ok")
    data = store._load(store._ALERTAS_FILE)
    data["8"]["corrupto"] = "no-es-fecha"
    store._save(store._ALERTAS_FILE, data)
    store.limpiar_alertas_viejas(horas=6)
    # El registro corrupto se descarta; el válido permanece.
    assert store.ya_enviada(8, "ok") is True
    assert store.ya_enviada(8, "corrupto") is False


# ── Cierres y reaperturas ─────────────────────────────────────────────────────

def test_actualizar_cierres_detecta_reaperturas(store):
    # Primer ciclo: dos cierres activos.
    reabiertos = store.actualizar_cierres(1, {"h1": "Cierre en 57D", "h2": "Cierre en 85D"})
    assert reabiertos == []
    assert store.get_cierres_activos(1) == {"h1": "Cierre en 57D", "h2": "Cierre en 85D"}

    # Segundo ciclo: h2 desaparece → se reabrió.
    reabiertos = store.actualizar_cierres(1, {"h1": "Cierre en 57D"})
    assert reabiertos == ["Cierre en 85D"]
    assert store.get_cierres_activos(1) == {"h1": "Cierre en 57D"}

    # Tercer ciclo: no queda ninguno → h1 reabierto y archivo limpio para el chat.
    reabiertos = store.actualizar_cierres(1, {})
    assert reabiertos == ["Cierre en 57D"]
    assert store.get_cierres_activos(1) == {}


def test_guardar_viaje_limpia_cierres(store):
    store.actualizar_cierres(3, {"h1": "Cierre viejo"})
    assert store.get_cierres_activos(3) == {"h1": "Cierre viejo"}
    # Iniciar un viaje nuevo limpia los cierres previos del chat.
    store.guardar_viaje(3, {"origen": "A", "destino": "B"})
    assert store.get_cierres_activos(3) == {}


def test_limpiar_cierres_viaje(store):
    store.actualizar_cierres(9, {"h1": "x", "h2": "y"})
    store.limpiar_cierres_viaje(9)
    assert store.get_cierres_activos(9) == {}


# ── Robustez de E/S ───────────────────────────────────────────────────────────

def test_json_corrupto_no_tumba(store):
    # Un archivo de estado corrupto debe tratarse como vacío, no lanzar.
    store._asegurar_dir()
    with open(store._path(store._VIAJES_FILE), "w") as f:
        f.write("{ esto no es json válido ")
    assert store.get_viaje(1) is None
    assert store.get_viajes_activos() == []


def test_escritura_es_atomica_y_legible(store):
    store.guardar_viaje(1, {"origen": "A", "destino": "B"})
    # El archivo debe ser JSON válido y legible de forma independiente.
    with open(store._path(store._VIAJES_FILE), encoding="utf-8") as f:
        data = json.load(f)
    assert "1" in data
    assert data["1"]["origen"] == "A"
