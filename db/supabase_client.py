"""
Persistencia en Supabase (PostgreSQL) — reemplaza SQLite.
"""
import os
import json
import hashlib
from datetime import datetime, timedelta, timezone
from supabase import create_client

_TZ_MX = timezone(timedelta(hours=-6))


def _campos_tiempo() -> dict:
    """Fecha, día de semana y hora en zona horaria México (UTC-6)."""
    ahora = datetime.now(_TZ_MX)
    return {
        "fecha":        ahora.date().isoformat(),
        "dia_semana":   ahora.isoweekday() % 7,  # 0=dom … 6=sab
        "hora_del_dia": ahora.hour,
    }


def _db():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


def guardar_viaje(chat_id: int, datos: dict):
    db = _db()
    db.table("viajes").upsert({
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
    # Limpiar cierres del viaje anterior para evitar falsos "reabiertos"
    db.table("cierres_activos").delete().eq("chat_id", chat_id).execute()


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


def get_cierres_activos(chat_id: int) -> dict[str, str]:
    """Retorna {hash_cierre: descripcion} de los cierres almacenados para este viaje."""
    res = (
        _db().table("cierres_activos")
        .select("hash_cierre, descripcion")
        .eq("chat_id", chat_id)
        .execute()
    )
    return {r["hash_cierre"]: r["descripcion"] for r in (res.data or [])}


def actualizar_cierres(chat_id: int, cierres_actuales: dict[str, str]) -> list[str]:
    """
    Sincroniza cierres activos con el estado actual de TomTom.
    - Nuevos cierres: registra en DB.
    - Cierres desaparecidos: elimina de DB y retorna sus descripciones.
    Retorna lista de descripciones de cierres que se reabrieron.
    """
    db = _db()
    previos = get_cierres_activos(chat_id)

    reabiertos_hashes = [h for h in previos if h not in cierres_actuales]
    reabiertos_desc   = [previos[h] for h in reabiertos_hashes]

    if reabiertos_hashes:
        db.table("cierres_activos").delete().eq(
            "chat_id", chat_id
        ).in_("hash_cierre", reabiertos_hashes).execute()

    nuevos = [
        {"chat_id": chat_id, "hash_cierre": h, "descripcion": desc}
        for h, desc in cierres_actuales.items()
        if h not in previos
    ]
    if nuevos:
        db.table("cierres_activos").upsert(
            nuevos, on_conflict="chat_id,hash_cierre"
        ).execute()

    return reabiertos_desc


def limpiar_cierres_viaje(chat_id: int):
    """Elimina todos los cierres activos al detener el viaje."""
    _db().table("cierres_activos").delete().eq("chat_id", chat_id).execute()


def guardar_robos_sesnsp(registros: list[dict]):
    """Guarda datos mensuales de robo SESNSP. Dedup por (año, mes, entidad, municipio)."""
    if not registros:
        return
    _db().table("robos_sesnsp").upsert(
        registros,
        on_conflict="año,mes,entidad,municipio",
        ignore_duplicates=True,
    ).execute()


def registrar_clima_historico(registros: list[dict]):
    """Guarda snapshot de clima de las 55 ciudades. Dedup por (ciudad, fecha, hora_del_dia)."""
    if not registros:
        return
    campos = _campos_tiempo()
    filas  = [{**r, **campos} for r in registros]
    _db().table("clima_historico").upsert(
        filas,
        on_conflict="ciudad,fecha,hora_del_dia",
        ignore_duplicates=True,
    ).execute()


def registrar_flujo_historico(registros: list[dict]):
    """Guarda snapshot de flujo vial de las 55 ciudades. Dedup por (ciudad, fecha, hora_del_dia)."""
    if not registros:
        return
    campos = _campos_tiempo()
    filas  = [{**r, **campos} for r in registros]
    _db().table("flujo_historico").upsert(
        filas,
        on_conflict="ciudad,fecha,hora_del_dia",
        ignore_duplicates=True,
    ).execute()


def registrar_incidentes_historico(
    incidentes: list[dict],
    origen: str = "",
    destino: str = "",
    city_path: list[str] | None = None,
):
    """
    Guarda incidentes en el histórico para el dataset de tesis.
    Dedup por (hash_contenido, fecha) — un registro por incidente por día.
    Inserta en lote y silencia conflictos de duplicados.
    """
    if not incidentes:
        return

    registros = []
    for inc in incidentes:
        desc = inc.get("descripcion", "")
        tipo = inc.get("tipo", "")
        raw  = f"{tipo}|{desc[:100]}"
        h    = hashlib.md5(raw.encode()).hexdigest()[:16]

        coords_lat = coords_lon = None
        if inc.get("coords"):
            coords_lat, coords_lon = inc["coords"]

        # Corredor: origen/destino/carretera pueden venir por incidente
        # (harvest de corredores) o por parámetro (monitor de viajes).
        inc_origen    = inc.get("_origen")    or origen
        inc_destino   = inc.get("_destino")   or destino
        inc_carretera = inc.get("_carretera")

        registros.append({
            **_campos_tiempo(),
            "origen":         inc_origen,
            "destino":        inc_destino,
            "city_path":      city_path,
            "carretera":      inc_carretera,
            "tipo":           tipo,
            "descripcion":    desc,
            "severidad":      int(inc.get("severidad", 0)),
            "fuente":         inc.get("fuente", "TomTom"),
            "hora_incidente": inc.get("hora"),
            "coords_lat":     coords_lat,
            "coords_lon":     coords_lon,
            "hash_contenido": h,
        })

    _db().table("incidentes_historico").upsert(
        registros,
        on_conflict="hash_contenido,fecha",
        ignore_duplicates=True,
    ).execute()
