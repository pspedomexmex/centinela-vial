"""
API de estadísticas agregadas para el dashboard.
GET /api/stats → JSON con datos de incidentes, flujo y clima.
"""
import os
import json
from http.server import BaseHTTPRequestHandler
from supabase import create_client


def _db():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


def _get_stats() -> dict:
    db = _db()

    # ── Totales ────────────────────────────────────────────────────
    total_res = db.table("incidentes_historico").select("id", count="exact").execute()
    total_inc = total_res.count or 0

    dias_res  = db.table("incidentes_historico").select("fecha").order("fecha").limit(1).execute()
    primer_dia = dias_res.data[0]["fecha"] if dias_res.data else "—"

    # ── Incidentes por tipo ────────────────────────────────────────
    tipo_res = (
        db.table("incidentes_historico")
        .select("tipo")
        .not_.is_("tipo", "null")
        .limit(5000)
        .execute()
    )
    tipo_count: dict[str, int] = {}
    for r in tipo_res.data:
        t = r["tipo"] or "Desconocido"
        tipo_count[t] = tipo_count.get(t, 0) + 1
    por_tipo = sorted(
        [{"tipo": k, "total": v} for k, v in tipo_count.items()],
        key=lambda x: -x["total"],
    )[:10]

    # ── Incidentes por carretera ───────────────────────────────────
    carr_res = (
        db.table("incidentes_historico")
        .select("carretera")
        .not_.is_("carretera", "null")
        .limit(5000)
        .execute()
    )
    carr_count: dict[str, int] = {}
    for r in carr_res.data:
        c = r["carretera"]
        if c:
            carr_count[c] = carr_count.get(c, 0) + 1
    por_carretera = sorted(
        [{"carretera": k, "total": v} for k, v in carr_count.items()],
        key=lambda x: -x["total"],
    )[:12]

    # ── Incidentes por hora del día ────────────────────────────────
    hora_res = (
        db.table("incidentes_historico")
        .select("hora_del_dia")
        .not_.is_("hora_del_dia", "null")
        .limit(5000)
        .execute()
    )
    hora_count: dict[int, int] = {}
    for r in hora_res.data:
        h = r["hora_del_dia"]
        if h is not None:
            hora_count[int(h)] = hora_count.get(int(h), 0) + 1
    por_hora = [{"hora": h, "total": hora_count.get(h, 0)} for h in range(24)]

    # ── Flujo por ciudad (último snapshot) ────────────────────────
    flujo_res = (
        db.table("flujo_historico")
        .select("ciudad,ratio_flujo,nivel,velocidad_actual,velocidad_libre")
        .order("registrado_en", desc=True)
        .limit(300)
        .execute()
    )
    flujo_ciudad: dict[str, list] = {}
    for r in flujo_res.data:
        c = r["ciudad"]
        if c and r["ratio_flujo"] is not None:
            flujo_ciudad.setdefault(c, []).append(r["ratio_flujo"])
    flujo_resumen = sorted(
        [{"ciudad": c, "ratio": round(sum(v) / len(v), 3)} for c, v in flujo_ciudad.items()],
        key=lambda x: x["ratio"],
    )[:15]

    # ── Incidentes por día de semana ──────────────────────────────
    dow_res = (
        db.table("incidentes_historico")
        .select("dia_semana")
        .not_.is_("dia_semana", "null")
        .limit(5000)
        .execute()
    )
    dow_count: dict[int, int] = {}
    for r in dow_res.data:
        d = r["dia_semana"]
        if d is not None:
            dow_count[int(d)] = dow_count.get(int(d), 0) + 1
    dias = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"]
    por_dow = [{"dia": dias[d], "total": dow_count.get(d, 0)} for d in range(7)]

    # ── Días con recolección completa (≥ 3 cosechas distintas) ──────
    flujo_fechas = (
        db.table("flujo_historico")
        .select("fecha,hora_del_dia")
        .not_.is_("fecha", "null")
        .execute()
    )
    dias_horas: dict[str, set] = {}
    for r in flujo_fechas.data:
        f = r["fecha"]
        h = r["hora_del_dia"]
        if f and h is not None:
            dias_horas.setdefault(f, set()).add(int(h))
    dias_completos = sum(1 for horas in dias_horas.values() if len(horas) >= 3)

    # ── Últimos 25 incidentes ─────────────────────────────────────
    recientes = (
        db.table("incidentes_historico")
        .select("tipo,descripcion,carretera,origen,destino,hora_del_dia,fecha")
        .order("registrado_en", desc=True)
        .limit(25)
        .execute()
    ).data

    # ── Incidentes con coords para el mapa ────────────────────────
    mapa = (
        db.table("incidentes_historico")
        .select("tipo,descripcion,coords_lat,coords_lon,carretera")
        .not_.is_("coords_lat", "null")
        .order("registrado_en", desc=True)
        .limit(150)
        .execute()
    ).data

    return {
        "resumen": {"total_incidentes": total_inc, "primer_dia": primer_dia},
        "dias_completos": dias_completos,
        "por_tipo": por_tipo,
        "por_carretera": por_carretera,
        "por_hora": por_hora,
        "por_dow": por_dow,
        "flujo_resumen": flujo_resumen,
        "recientes": recientes,
        "mapa": mapa,
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            data  = _get_stats()
            body  = json.dumps(data, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def log_message(self, *args):
        pass
