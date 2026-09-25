"""
Persistencia en Supabase (PostgreSQL) — reemplaza SQLite.
"""
import os
import json
from datetime import datetime, timedelta
from supabase import create_client


def _db():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


def guardar_viaje(chat_id: int, datos: dict):
    _db().table("viajes").upsert({
        "chat_id": chat_id,
        "origen": datos["origen"],
        "destino": datos["destino"],
        "origen_fmt": datos.get("origen_fmt", ""),
        "destino_fmt": datos.get("destino_fmt", ""),
        "regiones": datos.get("regiones", []),
        "estados": datos.get("estados", []),
        "distancia_km": datos.get("distancia_km"),
        "duracion_hrs": datos.get("duracion_hrs"),
        "city_path": datos.get("city_path"),
        "activo": True,
    }, on_conflict="chat_id").execute()


def get_viaje(chat_id: int) -> dict | None:
    res = (
        _db().table("viajes")
        .select("*")
        .eq("chat_id", chat_id)
        .eq("activo", True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def get_viajes_activos() -> list[dict]:
    res = _db().table("viajes").select("*").eq("activo", True).execute()
    return res.data or []


def detener_viaje(chat_id: int):
    _db().table("viajes").update({"activo": False}).eq("chat_id", chat_id).execute()


def ya_enviada(chat_id: int, hash_alerta: str) -> bool:
    res = (
        _db().table("alertas_enviadas")
        .select("id")
        .eq("chat_id", chat_id)
        .eq("hash_alerta", hash_alerta)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def marcar_enviada(chat_id: int, hash_alerta: str):
    _db().table("alertas_enviadas").upsert({
        "chat_id": chat_id,
        "hash_alerta": hash_alerta,
    }).execute()


def limpiar_alertas_viejas(horas: int = 6):
    cutoff = (datetime.utcnow() - timedelta(hours=horas)).isoformat()
    _db().table("alertas_enviadas").delete().lt("enviado_en", cutoff).execute()
