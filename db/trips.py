"""
Persistencia de viajes activos usando SQLite.
"""
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "/tmp/centinela_vial.db")


def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS viajes (
                chat_id     INTEGER PRIMARY KEY,
                origen      TEXT NOT NULL,
                destino     TEXT NOT NULL,
                origen_fmt  TEXT,
                destino_fmt TEXT,
                regiones    TEXT NOT NULL,
                estados     TEXT NOT NULL,
                distancia_km INTEGER,
                duracion_hrs REAL,
                creado_en   TEXT NOT NULL,
                activo      INTEGER DEFAULT 1
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS alertas_enviadas (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL,
                hash_alerta TEXT NOT NULL,
                enviado_en  TEXT NOT NULL
            )
        """)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_alertas_chat ON alertas_enviadas(chat_id, hash_alerta)"
        )


def guardar_viaje(chat_id: int, datos: dict):
    with _conn() as con:
        con.execute("""
            INSERT OR REPLACE INTO viajes
            (chat_id, origen, destino, origen_fmt, destino_fmt,
             regiones, estados, distancia_km, duracion_hrs, creado_en, activo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            chat_id,
            datos["origen"],
            datos["destino"],
            datos.get("origen_fmt", ""),
            datos.get("destino_fmt", ""),
            json.dumps(datos.get("regiones", [])),
            json.dumps(datos.get("estados", [])),
            datos.get("distancia_km"),
            datos.get("duracion_hrs"),
            datetime.now().isoformat(),
        ))


def get_viaje(chat_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM viajes WHERE chat_id = ? AND activo = 1", (chat_id,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["regiones"] = json.loads(d["regiones"])
    d["estados"] = json.loads(d["estados"])
    return d


def get_viajes_activos() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM viajes WHERE activo = 1").fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["regiones"] = json.loads(d["regiones"])
        d["estados"] = json.loads(d["estados"])
        result.append(d)
    return result


def detener_viaje(chat_id: int):
    with _conn() as con:
        con.execute("UPDATE viajes SET activo = 0 WHERE chat_id = ?", (chat_id,))


def ya_enviada(chat_id: int, hash_alerta: str) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM alertas_enviadas WHERE chat_id = ? AND hash_alerta = ?",
            (chat_id, hash_alerta),
        ).fetchone()
    return row is not None


def marcar_enviada(chat_id: int, hash_alerta: str):
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO alertas_enviadas (chat_id, hash_alerta, enviado_en) VALUES (?, ?, ?)",
            (chat_id, hash_alerta, datetime.now().isoformat()),
        )


def limpiar_alertas_viejas(horas: int = 6):
    """Elimina registro de alertas enviadas hace más de N horas para no bloquear re-alertas."""
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(hours=horas)).isoformat()
    with _conn() as con:
        con.execute("DELETE FROM alertas_enviadas WHERE enviado_en < ?", (cutoff,))
