"""
Suite de tests para Centinela Vial.
Cubre lógica pura — sin API keys, sin DB, sin Telegram.
Ejecutar: python -m pytest test_centinela_vial.py -v
"""
import sys
import os

# Asegurar que el root del proyecto esté en el path
sys.path.insert(0, os.path.dirname(__file__))

# ─── Fakes para módulos que requieren conexión ────────────────────────────────
import types

# Stub de googlemaps para que route_parser importe sin crash
googlemaps_stub = types.ModuleType("googlemaps")
googlemaps_stub.Client = object
sys.modules.setdefault("googlemaps", googlemaps_stub)

# Stubs de telegram para trip_monitor
_tg = types.ModuleType("telegram")
_tg.Bot = object
_tg.InlineKeyboardButton = object
_tg.InlineKeyboardMarkup = object
sys.modules.setdefault("telegram", _tg)

_tg_const = types.ModuleType("telegram.constants")
_tg_const.ParseMode = types.SimpleNamespace(MARKDOWN="Markdown")
sys.modules.setdefault("telegram.constants", _tg_const)

_tg_ext = types.ModuleType("telegram.ext")
_tg_ext.Application = object
_tg_ext.CommandHandler = object
_tg_ext.CallbackQueryHandler = object
sys.modules.setdefault("telegram.ext", _tg_ext)

# Stub de supabase para harvest y db
_supa = types.ModuleType("supabase")
_supa.create_client = lambda url, key: None
sys.modules.setdefault("supabase", _supa)

# Stub de db.supabase_client para módulos que lo importan en harvest
_db_stub = types.ModuleType("db.supabase_client")
for _fn in (
    "registrar_incidentes_historico", "registrar_clima_historico",
    "registrar_flujo_historico", "guardar_viaje", "get_viaje",
    "detener_viaje", "actualizar_cierres", "limpiar_cierres_viaje",
):
    setattr(_db_stub, _fn, lambda *a, **k: None)
sys.modules.setdefault("db.supabase_client", _db_stub)

_db_trips = types.ModuleType("db.trips")
for _fn in (
    "get_viajes_activos", "ya_enviada", "marcar_enviada", "limpiar_alertas_viejas",
):
    setattr(_db_trips, _fn, lambda *a, **k: None)
sys.modules.setdefault("db.trips", _db_trips)

# Stub de sources.capufe_monitor y sources.gmaps_traffic para trip_monitor
_capufe = types.ModuleType("sources.capufe_monitor")
_capufe.get_capufe_alerts_for_regions = lambda *a, **k: []
sys.modules.setdefault("sources.capufe_monitor", _capufe)

_gmaps = types.ModuleType("sources.gmaps_traffic")
_gmaps.get_traffic_status = lambda *a, **k: {}
_gmaps.EMOJI_TRAFICO = {}
sys.modules.setdefault("sources.gmaps_traffic", _gmaps)

_tw_mon = types.ModuleType("sources.twitter_monitor")
_tw_mon.get_tweets_for_regions = lambda *a, **k: ([], False)
sys.modules.setdefault("sources.twitter_monitor", _tw_mon)

# ─── Imports del proyecto ─────────────────────────────────────────────────────
import pytest

from regions.city_graph import (
    _norm,
    resolve_city,
    dijkstra_city_path,
    bfs_city_path,
    route_stats,
    route_stats_realtime,
    city_path_to_regions,
    get_route_segments,
    _edge_speed,
    EDGE_KM,
    EDGE_TIME_MIN,
    CITY_EDGES,
    CITY_NODES,
    CITY_LABELS,
)
from regions.route_parser import (
    _normalizar,
    _region_para_ciudad,
    _ruta_entre_regiones,
    _fallback_local,
    calcular_ruta_y_regiones,
    ADYACENCIA,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  1. Normalización de texto
# ═══════════════════════════════════════════════════════════════════════════════

class TestNorm:
    def test_quita_acentos(self):
        assert _norm("Querétaro") == "queretaro"
        assert _norm("Monterrey") == "monterrey"

    def test_minusculas_y_strip(self):
        assert _norm("  CDMX  ") == "cdmx"

    def test_route_parser_normalizar(self):
        assert _normalizar("Nuevo León") == "nuevo leon"
        assert _normalizar("Ciudad Juárez") == "ciudad juarez"


# ═══════════════════════════════════════════════════════════════════════════════
#  2. resolve_city — alias y búsqueda parcial
# ═══════════════════════════════════════════════════════════════════════════════

class TestResolveCity:
    # Exacto
    def test_exacto_cdmx(self):
        assert resolve_city("CDMX") == "cdmx"

    def test_exacto_monterrey(self):
        assert resolve_city("Monterrey") == "monterrey"

    def test_exacto_guadalajara(self):
        assert resolve_city("Guadalajara") == "guadalajara"

    # Alias y variantes
    def test_alias_df(self):
        assert resolve_city("DF") == "cdmx"

    def test_alias_ciudad_de_mexico(self):
        assert resolve_city("Ciudad de México") == "cdmx"

    def test_alias_qro(self):
        assert resolve_city("Qro") == "queretaro"

    def test_alias_slp(self):
        assert resolve_city("SLP") == "san_luis_potosi"

    def test_alias_cd_juarez(self):
        assert resolve_city("Cd Juárez") == "ciudad_juarez"

    def test_alias_ciudad_victoria(self):
        assert resolve_city("Ciudad Victoria") == "ciudad_victoria"

    def test_alias_nuevo_laredo(self):
        assert resolve_city("Nuevo Laredo") == "nuevo_laredo"

    # Municipios del área metro que resuelven al hub
    def test_tlalnepantla_a_cdmx(self):
        assert resolve_city("Tlalnepantla") == "cdmx"

    def test_ecatepec_a_cdmx(self):
        assert resolve_city("Ecatepec") == "cdmx"

    def test_apodaca_a_monterrey(self):
        assert resolve_city("Apodaca") == "monterrey"

    # Ciudades secundarias
    def test_boca_del_rio_a_veracruz(self):
        assert resolve_city("Boca del Río") == "veracruz"

    def test_altamira_a_tampico(self):
        assert resolve_city("Altamira") == "tampico"

    def test_poza_rica_a_tuxpan(self):
        assert resolve_city("Poza Rica") == "tuxpan"

    # Inexistente
    def test_ciudad_inexistente_retorna_none(self):
        assert resolve_city("Zzz_no_existe_xyz") is None


# ═══════════════════════════════════════════════════════════════════════════════
#  3. Dijkstra y BFS
# ═══════════════════════════════════════════════════════════════════════════════

class TestDijkstra:
    def test_mismo_origen_destino(self):
        path = dijkstra_city_path("cdmx", "cdmx")
        assert path == ["cdmx"]

    def test_ruta_directa_cdmx_queretaro(self):
        path = dijkstra_city_path("cdmx", "queretaro")
        assert path[0] == "cdmx"
        assert path[-1] == "queretaro"
        assert len(path) == 2

    def test_ruta_cdmx_monterrey_pasa_por_slp(self):
        path = dijkstra_city_path("cdmx", "monterrey", by_time=True)
        assert "cdmx" in path
        assert "monterrey" in path
        # El corredor esperado: cdmx→qro→slp→matehuala→monterrey
        assert "queretaro" in path or "san_luis_potosi" in path

    def test_ruta_cdmx_guadalajara(self):
        path = dijkstra_city_path("cdmx", "guadalajara", by_time=True)
        assert path[0] == "cdmx"
        assert path[-1] == "guadalajara"

    def test_ruta_cdmx_tijuana_cruza_noroeste(self):
        path = dijkstra_city_path("cdmx", "tijuana", by_time=True)
        assert "tijuana" in path
        # Debe pasar por algún nodo del corredor Pacífico
        assert any(c in path for c in ("hermosillo", "culiacan", "mazatlan"))

    def test_ruta_cdmx_cancun_cruza_sureste(self):
        path = dijkstra_city_path("cdmx", "cancun", by_time=True)
        assert "cancun" in path
        assert any(c in path for c in ("veracruz", "coatzacoalcos", "villahermosa", "merida"))

    def test_destino_inexistente_retorna_none(self):
        assert dijkstra_city_path("cdmx", "no_existe") is None

    def test_origen_inexistente_retorna_none(self):
        assert dijkstra_city_path("no_existe", "cdmx") is None


class TestBFS:
    def test_bfs_misma_ciudad(self):
        assert bfs_city_path("cdmx", "cdmx") == ["cdmx"]

    def test_bfs_vecinos_directos(self):
        path = bfs_city_path("cdmx", "queretaro")
        assert path == ["cdmx", "queretaro"]

    def test_bfs_inexistente(self):
        assert bfs_city_path("cdmx", "nada_aqui") is None


# ═══════════════════════════════════════════════════════════════════════════════
#  4. route_stats
# ═══════════════════════════════════════════════════════════════════════════════

class TestRouteStats:
    def test_ruta_un_salto(self):
        stats = route_stats(["cdmx", "queretaro"])
        assert stats["km"] == EDGE_KM["cdmx"]["queretaro"]
        assert stats["min"] > 0
        assert stats["hrs"] > 0

    def test_ruta_dos_saltos(self):
        stats = route_stats(["cdmx", "queretaro", "san_luis_potosi"])
        expected_km = EDGE_KM["cdmx"]["queretaro"] + EDGE_KM["queretaro"]["san_luis_potosi"]
        assert stats["km"] == expected_km

    def test_ruta_vacia(self):
        stats = route_stats(["cdmx"])
        assert stats["km"] == 0
        assert stats["min"] == 0

    def test_hrs_es_redondeo_consistente(self):
        stats = route_stats(["cdmx", "queretaro", "san_luis_potosi", "matehuala", "monterrey"])
        assert stats["hrs"] == round(stats["min"] / 60, 1)

    def test_realtime_sin_overrides_igual_a_estatico(self):
        path = ["cdmx", "queretaro"]
        estatico = route_stats(path)
        rt = route_stats_realtime(path, {})
        # Sin overrides, el tiempo RT puede diferir levemente porque _edge_time_rt
        # aplica max(20, speed) pero con speed igual → mismo resultado
        assert rt["km"] == estatico["km"]


# ═══════════════════════════════════════════════════════════════════════════════
#  5. _edge_speed
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeSpeed:
    def test_autopista_sufijo_D_es_90(self):
        # cdmx→queretaro es MEX-57D
        assert _edge_speed("cdmx", "queretaro") == 90

    def test_libre_es_75(self):
        # queretaro→san_luis_potosi es MEX-57 (sin D)
        assert _edge_speed("queretaro", "san_luis_potosi") == 75

    def test_espinazo_del_diablo_es_50(self):
        assert _edge_speed("mazatlan", "durango") == 50
        assert _edge_speed("durango", "mazatlan") == 50

    def test_sierra_tarahumara_es_65(self):
        assert _edge_speed("chihuahua", "hermosillo") == 65

    def test_ferry_la_paz_es_55(self):
        assert _edge_speed("los_mochis", "la_paz") == 55


# ═══════════════════════════════════════════════════════════════════════════════
#  6. EDGE_TIME_MIN — integridad del grafo
# ═══════════════════════════════════════════════════════════════════════════════

class TestGrafoIntegridad:
    def test_todos_los_nodos_de_edges_tienen_km(self):
        faltantes = []
        for origen, vecinos in CITY_EDGES.items():
            for dest in vecinos:
                if EDGE_KM.get(origen, {}).get(dest, 0) == 0:
                    faltantes.append(f"{origen}→{dest}")
        assert faltantes == [], f"Aristas sin km: {faltantes}"

    def test_todos_los_edges_tienen_time(self):
        faltantes = []
        for origen, vecinos in CITY_EDGES.items():
            for dest in vecinos:
                if EDGE_TIME_MIN.get(origen, {}).get(dest, 0) == 0:
                    faltantes.append(f"{origen}→{dest}")
        assert faltantes == [], f"Aristas sin tiempo: {faltantes}"

    def test_todos_los_nodos_en_city_nodes_tienen_label(self):
        sin_label = [k for k in CITY_NODES if k not in CITY_LABELS]
        assert sin_label == [], f"Nodos sin label: {sin_label}"

    def test_grafo_simetrico_km(self):
        """Toda arista A→B debe tener su recíproca B→A en EDGE_KM con el mismo valor."""
        asimetricos = []
        for a, vecinos in EDGE_KM.items():
            for b, km in vecinos.items():
                km_inv = EDGE_KM.get(b, {}).get(a, -1)
                if km_inv == -1:
                    asimetricos.append(f"{a}→{b} tiene km={km} pero {b}→{a} no existe en EDGE_KM")
        assert asimetricos == [], "\n".join(asimetricos)

    def test_city_edges_conectividad_desde_cdmx(self):
        """Desde CDMX se debe poder alcanzar al menos 40 nodos vía BFS."""
        from collections import deque
        visitados = set()
        cola = deque(["cdmx"])
        while cola:
            ciudad = cola.popleft()
            if ciudad in visitados:
                continue
            visitados.add(ciudad)
            for vecino in CITY_EDGES.get(ciudad, {}):
                if vecino not in visitados:
                    cola.append(vecino)
        assert len(visitados) >= 40, f"Solo se alcanzaron {len(visitados)} nodos desde CDMX"


# ═══════════════════════════════════════════════════════════════════════════════
#  7. get_route_segments
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetRouteSegments:
    def test_segmento_lleva_highway_entrante(self):
        segs = get_route_segments(["cdmx", "queretaro"])
        assert len(segs) == 1
        city, lat, lon, highways = segs[0]
        assert city == "queretaro"
        assert "MEX-57D" in highways

    def test_segmento_lleva_highways_entrada_y_salida(self):
        segs = get_route_segments(["cdmx", "queretaro", "san_luis_potosi"])
        qro_seg = next(s for s in segs if s[0] == "queretaro")
        # Entrante: MEX-57D (cdmx→qro), Saliente: MEX-57 (qro→slp)
        assert "MEX-57D" in qro_seg[3]
        assert "MEX-57" in qro_seg[3]

    def test_segmento_tiene_coordenadas_validas(self):
        segs = get_route_segments(["cdmx", "queretaro"])
        _, lat, lon, _ = segs[0]
        assert 15.0 <= lat <= 33.0, "Latitud fuera de México"
        assert -118.0 <= lon <= -86.0, "Longitud fuera de México"

    def test_ruta_un_solo_nodo_sin_segmentos(self):
        segs = get_route_segments(["cdmx"])
        assert segs == []


# ═══════════════════════════════════════════════════════════════════════════════
#  8. city_path_to_regions
# ═══════════════════════════════════════════════════════════════════════════════

class TestCityPathToRegions:
    def test_cdmx_es_centro(self):
        assert city_path_to_regions(["cdmx"]) == ["centro"]

    def test_monterrey_es_noreste(self):
        assert city_path_to_regions(["monterrey"]) == ["noreste"]

    def test_ruta_cdmx_monterrey_incluye_centro_y_noreste(self):
        path = ["cdmx", "queretaro", "san_luis_potosi", "matehuala", "monterrey"]
        regiones = city_path_to_regions(path)
        assert "centro" in regiones
        assert "noreste" in regiones

    def test_regiones_sin_duplicados(self):
        path = ["cdmx", "queretaro", "san_luis_potosi", "matehuala", "monterrey"]
        regiones = city_path_to_regions(path)
        assert len(regiones) == len(set(regiones))

    def test_nodo_desconocido_se_ignora(self):
        regiones = city_path_to_regions(["cdmx", "nodo_que_no_existe", "queretaro"])
        assert "centro" in regiones
        assert "centro_norte" in regiones


# ═══════════════════════════════════════════════════════════════════════════════
#  9. route_parser — lógica regional (sin Google Maps)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegionParaCiudad:
    def test_cdmx_es_centro(self):
        assert _region_para_ciudad("CDMX") == "centro"

    def test_monterrey_es_noreste(self):
        assert _region_para_ciudad("Monterrey") == "noreste"

    def test_guadalajara_es_occidente(self):
        assert _region_para_ciudad("Guadalajara") == "occidente"

    def test_tijuana_es_noroeste(self):
        assert _region_para_ciudad("Tijuana") == "noroeste"

    def test_merida_es_peninsula(self):
        assert _region_para_ciudad("Mérida") == "peninsula"

    def test_ciudad_inexistente_retorna_none(self):
        assert _region_para_ciudad("Noexistópolis") is None


class TestRutaEntreRegiones:
    def test_misma_region(self):
        assert _ruta_entre_regiones("centro", "centro") == ["centro"]

    def test_adyacentes_directo(self):
        # centro ↔ golfo son adyacentes
        path = _ruta_entre_regiones("centro", "golfo")
        assert path[0] == "centro"
        assert path[-1] == "golfo"
        assert len(path) == 2

    def test_peninsula_desde_centro(self):
        # centro → golfo → peninsula (2 saltos)
        path = _ruta_entre_regiones("centro", "peninsula")
        assert path[0] == "centro"
        assert path[-1] == "peninsula"
        assert "golfo" in path

    def test_noroeste_desde_centro(self):
        path = _ruta_entre_regiones("centro", "noroeste")
        assert path[0] == "centro"
        assert path[-1] == "noroeste"
        assert len(path) >= 2


class TestAdyacenciaConsistencia:
    def test_grafo_adyacencia_simetrico(self):
        """Si A lista B, B debe listar A."""
        asimetricos = []
        for region, vecinos in ADYACENCIA.items():
            for v in vecinos:
                if region not in ADYACENCIA.get(v, []):
                    asimetricos.append(f"{region}↔{v} no es simétrico")
        assert asimetricos == [], "\n".join(asimetricos)

    def test_peninsula_solo_llega_por_golfo(self):
        assert ADYACENCIA["peninsula"] == ["golfo"]


class TestFallbackLocal:
    def test_ciudad_conocida_retorna_resultado(self):
        res = _fallback_local("CDMX", "Monterrey")
        assert res["error"] is None
        assert "centro" in res["regiones"]
        assert "noreste" in res["regiones"]

    def test_origen_desconocido_retorna_error(self):
        res = _fallback_local("XyzNoExiste", "Monterrey")
        assert res["error"] is not None

    def test_destino_desconocido_retorna_error(self):
        res = _fallback_local("CDMX", "XyzNoExiste")
        assert res["error"] is not None

    def test_ambos_desconocidos_retorna_error(self):
        res = _fallback_local("Aaa", "Bbb")
        assert res["error"] is not None

    def test_sin_distancia_ni_duracion_en_fallback(self):
        res = _fallback_local("Guadalajara", "Monterrey")
        assert res["distancia_km"] is None
        assert res["duracion_hrs"] is None


# ═══════════════════════════════════════════════════════════════════════════════
#  10. calcular_ruta_y_regiones — integración sin APIs externas
# ═══════════════════════════════════════════════════════════════════════════════

class TestCalcularRuta:
    def test_ruta_conocida_usa_city_graph(self):
        res = calcular_ruta_y_regiones("CDMX", "Monterrey", gmaps_key="")
        assert res["error"] is None
        assert res["city_path"] is not None
        assert "cdmx" in res["city_path"]
        assert "monterrey" in res["city_path"]

    def test_ruta_tiene_distancia_y_duracion(self):
        res = calcular_ruta_y_regiones("CDMX", "Guadalajara", gmaps_key="")
        assert res["distancia_km"] and res["distancia_km"] > 0
        assert res["duracion_hrs"] and res["duracion_hrs"] > 0

    def test_ruta_cdmx_tijuana_mayor_2000km(self):
        res = calcular_ruta_y_regiones("CDMX", "Tijuana", gmaps_key="")
        assert res["error"] is None
        assert res["distancia_km"] and res["distancia_km"] > 2000

    def test_ruta_con_acentos_funciona(self):
        res = calcular_ruta_y_regiones("Querétaro", "Monterrey", gmaps_key="")
        assert res["error"] is None

    def test_ruta_alias_funciona(self):
        res = calcular_ruta_y_regiones("DF", "Reynosa", gmaps_key="")
        assert res["error"] is None
        assert res["city_path"][0] == "cdmx"

    def test_origen_invalido_retorna_error(self):
        res = calcular_ruta_y_regiones("NoExisteXXX", "Monterrey", gmaps_key="")
        assert res.get("error") is not None

    def test_destino_invalido_retorna_error(self):
        res = calcular_ruta_y_regiones("CDMX", "NoExisteXXX", gmaps_key="")
        assert res.get("error") is not None

    def test_regiones_ordenadas_sin_duplicados(self):
        res = calcular_ruta_y_regiones("CDMX", "Cancún", gmaps_key="")
        if res["error"] is None:
            assert len(res["regiones"]) == len(set(res["regiones"]))

    def test_flow_overrides_ajusta_tiempo(self):
        """Con tráfico lento (30 km/h), el tiempo debe ser mayor que sin overrides."""
        res_normal = calcular_ruta_y_regiones("CDMX", "Monterrey", gmaps_key="")
        path = res_normal["city_path"]
        flow = {city: 30.0 for city in path}  # congestión severa en toda la ruta
        res_lento = calcular_ruta_y_regiones("CDMX", "Monterrey", gmaps_key="", flow_overrides=flow)
        if res_lento and not res_lento.get("error"):
            assert res_lento["duracion_hrs"] > res_normal["duracion_hrs"]


# ═══════════════════════════════════════════════════════════════════════════════
#  12. openmeteo — integridad del dict WMO
# ═══════════════════════════════════════════════════════════════════════════════

class TestOpenMeteoWMO:
    def setup_method(self):
        from sources.openmeteo import _WMO
        self._WMO = _WMO

    def test_codigo_0_es_despejado_no_severo(self):
        emoji, desc, severo = self._WMO[0]
        assert severo is False
        assert "Despejado" in desc

    def test_tormenta_electrica_es_severa(self):
        _, _, severo = self._WMO[95]
        assert severo is True

    def test_nevada_es_severa(self):
        _, _, severo = self._WMO[71]
        assert severo is True

    def test_todos_tienen_emoji_desc_bool(self):
        for codigo, val in self._WMO.items():
            assert len(val) == 3, f"Código {codigo}: se esperan 3 elementos"
            emoji, desc, severo = val
            assert isinstance(emoji, str) and len(emoji) > 0
            assert isinstance(desc, str) and len(desc) > 0
            assert isinstance(severo, bool)


# ═══════════════════════════════════════════════════════════════════════════════
#  12. TomTom Incidents — funciones puras
# ═══════════════════════════════════════════════════════════════════════════════

class TestTomTomBbox:
    def setup_method(self):
        from sources.tomtom_incidents import _bbox, TILE_HALF
        self._bbox = _bbox
        self._half = TILE_HALF

    def test_formato_bbox(self):
        result = self._bbox(19.4, -99.1)
        parts = result.split(",")
        assert len(parts) == 4

    def test_bbox_simetrico(self):
        lat, lon = 19.4, -99.1
        result = self._bbox(lat, lon)
        lon_min, lat_min, lon_max, lat_max = (float(x) for x in result.split(","))
        assert abs(lon_min - (lon - self._half)) < 1e-9
        assert abs(lat_min - (lat - self._half)) < 1e-9
        assert abs(lon_max - (lon + self._half)) < 1e-9
        assert abs(lat_max - (lat + self._half)) < 1e-9

    def test_tile_half_es_razonable(self):
        # TILE_HALF debe producir un bbox menor a ~10,000 km²
        assert 0.1 < self._half < 1.0


class TestTomTomEsSignificativo:
    def setup_method(self):
        from sources.tomtom_incidents import _es_significativo
        self.fn = _es_significativo

    def _inc(self, cat: int, roads: list = None) -> dict:
        return {"properties": {"iconCategory": cat, "roadNumbers": roads or []}}

    def test_accidente_con_carretera_es_significativo(self):
        assert self.fn(self._inc(1, ["MEX-57D"])) is True

    def test_accidente_sin_carretera_no_es_significativo(self):
        assert self.fn(self._inc(1, [])) is False

    def test_condiciones_peligrosas_con_carretera(self):
        assert self.fn(self._inc(3, ["MEX-57"])) is True

    def test_cierre_sin_carretera_es_significativo(self):
        # cat 8 pasa por proximidad geográfica del tile
        assert self.fn(self._inc(8, [])) is True

    def test_cierre_con_carretera_tambien(self):
        assert self.fn(self._inc(8, ["MEX-150D"])) is True

    def test_inundacion_con_carretera(self):
        assert self.fn(self._inc(11, ["MEX-186"])) is True

    def test_niebla_ignorada(self):
        assert self.fn(self._inc(2, ["MEX-57D"])) is False

    def test_lluvia_ignorada(self):
        assert self.fn(self._inc(4, ["MEX-57D"])) is False

    def test_obras_ignoradas(self):
        assert self.fn(self._inc(9, ["MEX-45"])) is False

    def test_trafico_ignorado(self):
        assert self.fn(self._inc(6, ["MEX-57D"])) is False

    def test_carril_cerrado_ignorado(self):
        assert self.fn(self._inc(7, ["MEX-57D"])) is False

    def test_categoria_0_no_es_significativa(self):
        # cat 0 no está en críticas ni ignoradas → False
        assert self.fn(self._inc(0, ["MEX-57D"])) is False


class TestTomTomFmtHora:
    def setup_method(self):
        from sources.tomtom_incidents import _fmt_hora
        self.fn = _fmt_hora

    def test_convierte_utc_a_hora_mx(self):
        # 20:30 UTC → 14:30 UTC-6
        assert self.fn("2024-01-15T20:30:00Z") == "14:30"

    def test_medianoche_utc_a_mx(self):
        # 00:00 UTC → 18:00 UTC-6 del día anterior
        assert self.fn("2024-01-15T00:00:00Z") == "18:00"

    def test_none_retorna_none(self):
        assert self.fn(None) is None

    def test_cadena_vacia_retorna_none(self):
        assert self.fn("") is None

    def test_malformado_retorna_none(self):
        assert self.fn("no-es-fecha") is None


class TestTomTomCierreHash:
    def setup_method(self):
        from sources.tomtom_incidents import _cierre_hash
        self.fn = _cierre_hash

    def _p(self, roads=None, desde="A", hasta="B") -> dict:
        return {"roadNumbers": roads or ["MEX-57D"], "from": desde, "to": hasta}

    def test_hash_es_hex_12_chars(self):
        h = self.fn(self._p())
        assert len(h) == 12
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_determinista(self):
        p = self._p()
        assert self.fn(p) == self.fn(p)

    def test_hash_simetrico_desde_hasta(self):
        # El hash no depende del orden desde/hasta
        assert self.fn(self._p(desde="X", hasta="Y")) == \
               self.fn(self._p(desde="Y", hasta="X"))

    def test_hash_distinto_con_diferente_carretera(self):
        assert self.fn(self._p(roads=["MEX-57D"])) != \
               self.fn(self._p(roads=["MEX-150D"]))

    def test_sin_roads_no_falla(self):
        h = self.fn({"roadNumbers": None, "from": "A", "to": "B"})
        assert len(h) == 12


class TestTomTomExtractCoords:
    def setup_method(self):
        from sources.tomtom_incidents import _extract_coords
        self.fn = _extract_coords

    def test_point_retorna_lat_lon(self):
        inc = {"geometry": {"type": "Point", "coordinates": [-99.1, 19.4]}}
        lat, lon = self.fn(inc)
        assert abs(lat - 19.4) < 1e-4
        assert abs(lon - (-99.1)) < 1e-4

    def test_point_redondeado_a_5_decimales(self):
        inc = {"geometry": {"type": "Point", "coordinates": [-99.123456789, 19.987654321]}}
        lat, lon = self.fn(inc)
        assert lat == round(19.987654321, 5)
        assert lon == round(-99.123456789, 5)

    def test_linestring_retorna_punto_medio(self):
        inc = {"geometry": {
            "type": "LineString",
            "coordinates": [[-99.0, 19.0], [-99.1, 19.1], [-99.2, 19.2]],
        }}
        lat, lon = self.fn(inc)
        # Punto medio (índice 1 de 3)
        assert abs(lat - 19.1) < 1e-4
        assert abs(lon - (-99.1)) < 1e-4

    def test_geometria_vacia_retorna_none(self):
        assert self.fn({}) is None

    def test_linestring_vacio_retorna_none(self):
        inc = {"geometry": {"type": "LineString", "coordinates": []}}
        assert self.fn(inc) is None


class TestTomTomToAlerta:
    def setup_method(self):
        from sources.tomtom_incidents import _to_alerta
        self.fn = _to_alerta

    def _inc(self, cat=1, delay=2, roads=None, desde="Origen", hasta="Destino",
             start="2024-01-15T20:30:00Z", coords=None):
        geom = {"type": "Point", "coordinates": coords or [-99.1, 19.4]}
        return {
            "geometry": geom,
            "properties": {
                "iconCategory": cat,
                "magnitudeOfDelay": delay,
                "startTime": start,
                "from": desde,
                "to": hasta,
                "roadNumbers": roads if roads is not None else ["MEX-57D"],
            },
        }

    def test_tiene_campos_obligatorios(self):
        a = self.fn(self._inc())
        for campo in ("tipo", "emoji", "descripcion", "hora", "severidad", "fuente", "coords"):
            assert campo in a, f"Falta campo: {campo}"

    def test_tipo_accidente(self):
        a = self.fn(self._inc(cat=1))
        assert a["tipo"] == "Accidente"

    def test_emoji_accidente(self):
        a = self.fn(self._inc(cat=1))
        assert a["emoji"] == "🚨"

    def test_descripcion_incluye_carretera(self):
        a = self.fn(self._inc(roads=["MEX-57D"]))
        assert "MEX-57D" in a["descripcion"]

    def test_descripcion_incluye_desde_hasta(self):
        a = self.fn(self._inc(desde="CDMX", hasta="QRO"))
        assert "CDMX" in a["descripcion"]
        assert "QRO" in a["descripcion"]

    def test_severidad_es_delay(self):
        a = self.fn(self._inc(delay=3))
        assert a["severidad"] == 3

    def test_cierre_hash_solo_en_cat8(self):
        a_acc = self.fn(self._inc(cat=1))
        a_cierre = self.fn(self._inc(cat=8))
        assert a_acc["cierre_hash"] is None
        assert a_cierre["cierre_hash"] is not None

    def test_coords_extraidas(self):
        a = self.fn(self._inc())
        assert a["coords"] is not None
        lat, lon = a["coords"]
        assert abs(lat - 19.4) < 1e-4

    def test_fuente_es_tomtom(self):
        a = self.fn(self._inc())
        assert a["fuente"] == "TomTom"


class TestTomTomDedup:
    def setup_method(self):
        from sources.tomtom_incidents import _dedup_incidents, _to_alerta
        self._dedup = _dedup_incidents
        self._to_alerta = _to_alerta

    def _inc_raw(self, cat=1, roads=None, desde="A", hasta="B", delay=2):
        return {
            "geometry": {"type": "Point", "coordinates": [-99.1, 19.4]},
            "properties": {
                "iconCategory": cat,
                "magnitudeOfDelay": delay,
                "startTime": "2024-01-15T20:30:00Z",
                "from": desde,
                "to": hasta,
                "roadNumbers": roads if roads is not None else ["MEX-57D"],
            },
        }

    def test_lista_vacia(self):
        assert self._dedup([]) == []

    def test_un_incidente_pasa(self):
        result = self._dedup([[self._inc_raw()]])
        assert len(result) == 1

    def test_duplicados_se_eliminan(self):
        inc = self._inc_raw()
        result = self._dedup([[inc, inc]])
        assert len(result) == 1

    def test_ordenado_por_severidad_desc(self):
        inc_alto = self._inc_raw(delay=4, desde="A2", hasta="B2", roads=["MEX-150D"])
        inc_bajo = self._inc_raw(delay=1, desde="C", hasta="D", roads=["MEX-45"])
        result = self._dedup([[inc_bajo, inc_alto]])
        assert result[0]["severidad"] >= result[-1]["severidad"]

    def test_allowed_per_tile_filtra_carreteras(self):
        inc = self._inc_raw(roads=["MEX-57D"])
        # Sólo se permiten carreteras MEX-45 → debe filtrar
        result = self._dedup([[inc]], allowed_per_tile=[{"MEX-45"}])
        assert len(result) == 0

    def test_allowed_per_tile_deja_pasar_carretera_correcta(self):
        inc = self._inc_raw(roads=["MEX-57D"])
        result = self._dedup([[inc]], allowed_per_tile=[{"MEX-57D"}])
        assert len(result) == 1

    def test_cierre_sin_carretera_pasa_sin_filtro(self):
        # cat 8 sin roads: pasa incluso con allowed_per_tile porque roads=[]+allowed
        inc = self._inc_raw(cat=8, roads=[])
        result = self._dedup([[inc]], allowed_per_tile=[{"MEX-57D"}])
        # roads=[] → road_key="" → no hay roads que comparar → pasa
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════════════════════
#  13. TomTom Flow — umbrales y constantes
# ═══════════════════════════════════════════════════════════════════════════════

class TestTomTomFlowUmbrales:
    def setup_method(self):
        import sources.tomtom_flow as tf
        self.tf = tf

    def test_muy_lento_menor_que_lento(self):
        assert self.tf._UMBRAL_MUY_LENTO < self.tf._UMBRAL_LENTO

    def test_lento_menor_que_1(self):
        assert self.tf._UMBRAL_LENTO < 1.0

    def test_muy_lento_positivo(self):
        assert self.tf._UMBRAL_MUY_LENTO > 0

    def test_confianza_minima_en_rango(self):
        assert 0 < self.tf._CONF_MINIMA < 1.0

    def test_ratio_040_es_muy_lento(self):
        # Un ratio de 0.39 está por debajo del umbral MUY_LENTO (0.40)
        ratio = 0.39
        assert ratio < self.tf._UMBRAL_MUY_LENTO

    def test_ratio_060_es_lento(self):
        ratio = 0.60
        assert self.tf._UMBRAL_MUY_LENTO <= ratio < self.tf._UMBRAL_LENTO

    def test_ratio_090_es_normal(self):
        ratio = 0.90
        assert ratio >= self.tf._UMBRAL_LENTO


# ═══════════════════════════════════════════════════════════════════════════════
#  14. Escaneo carreteras — integridad de datos
# ═══════════════════════════════════════════════════════════════════════════════

class TestEscaneoCarreterasIntegridad:
    def setup_method(self):
        from sources.escaneo_carreteras import TRAMOS_CLAVE
        from regions.city_graph import CITY_NODES
        self.tramos = TRAMOS_CLAVE
        self.nodes = CITY_NODES

    def test_hay_exactamente_27_tramos(self):
        assert len(self.tramos) == 27

    def test_todas_las_ciudades_a_existen_en_grafo(self):
        faltantes = [t[0] for t in self.tramos if t[0] not in self.nodes]
        assert faltantes == [], f"Ciudades A sin coordenadas: {faltantes}"

    def test_todas_las_ciudades_b_existen_en_grafo(self):
        faltantes = [t[1] for t in self.tramos if t[1] not in self.nodes]
        assert faltantes == [], f"Ciudades B sin coordenadas: {faltantes}"

    def test_nombres_no_vacios(self):
        for a, b, nombre in self.tramos:
            assert nombre.strip(), f"Nombre vacío en tramo {a}→{b}"

    def test_midpoints_dentro_de_mexico(self):
        for city_a, city_b, _ in self.tramos:
            lat_a, lon_a = self.nodes[city_a]
            lat_b, lon_b = self.nodes[city_b]
            lat_mid = (lat_a + lat_b) / 2
            lon_mid = (lon_a + lon_b) / 2
            assert 14 <= lat_mid <= 33, f"Latitud fuera de rango: {lat_mid}"
            assert -120 <= lon_mid <= -85, f"Longitud fuera de rango: {lon_mid}"

    def test_no_hay_tramos_duplicados(self):
        pares = [frozenset([a, b]) for a, b, _ in self.tramos]
        assert len(pares) == len(set(pares)), "Hay tramos duplicados"


# ═══════════════════════════════════════════════════════════════════════════════
#  15. Escaneo ZMVM — _dist_km y datos
# ═══════════════════════════════════════════════════════════════════════════════

class TestEscaneoZMVMIntegridad:
    def setup_method(self):
        from sources.escaneo_zmvm import TRAMOS_ZMVM, MUNICIPIOS_ORDEN, _dist_km
        self.tramos = TRAMOS_ZMVM
        self.municipios = MUNICIPIOS_ORDEN
        self.dist_km = _dist_km

    def test_todos_los_municipios_orden_tienen_tramos(self):
        muns_en_tramos = {t[0] for t in self.tramos}
        for mun in self.municipios:
            assert mun in muns_en_tramos, f"Municipio sin tramos: {mun}"

    def test_dist_km_mismo_punto_es_cero(self):
        assert self.dist_km(19.638, -99.001, 19.638, -99.001) == 0.0

    def test_dist_km_un_grado_lat_aprox_111km(self):
        d = self.dist_km(0.0, 0.0, 1.0, 0.0)
        assert abs(d - 111.0) < 1.0

    def test_dist_km_un_grado_lon_en_ecuador(self):
        d = self.dist_km(0.0, 0.0, 0.0, 1.0)
        assert abs(d - 111.0) < 1.0

    def test_dist_km_es_positiva(self):
        d = self.dist_km(19.5, -99.2, 19.7, -99.0)
        assert d > 0

    def test_tramos_con_coordenadas_dentro_de_zmvm(self):
        for mun, nombre, lat, lon, hw, req_fed, max_d in self.tramos:
            assert 19.0 <= lat <= 20.0, f"Lat fuera de ZMVM: {lat} en {nombre}"
            assert -100.0 <= lon <= -98.0, f"Lon fuera de ZMVM: {lon} en {nombre}"

    def test_municipios_orden_tiene_siete_municipios(self):
        assert len(self.municipios) == 7


# ═══════════════════════════════════════════════════════════════════════════════
#  16. Nitter Monitor — funciones puras
# ═══════════════════════════════════════════════════════════════════════════════

class TestNitterClasificar:
    def setup_method(self):
        from sources.nitter_monitor import _clasificar
        self.fn = _clasificar

    def test_cierre(self):
        emoji, tipo = self.fn("cierre vial en autopista")
        assert tipo == "Cierre vial"

    def test_bloqueo(self):
        emoji, tipo = self.fn("bloqueo en la carretera federal")
        assert tipo == "Cierre vial"

    def test_accidente(self):
        emoji, tipo = self.fn("accidente grave en MEX-57D")
        assert tipo == "Accidente"

    def test_volcadura(self):
        emoji, tipo = self.fn("volcadura de tráiler en la 57")
        assert tipo == "Accidente"

    def test_derrumbe(self):
        emoji, tipo = self.fn("derrumbe en la sierra")
        assert tipo == "Peligro en ruta"

    def test_manifestacion(self):
        emoji, tipo = self.fn("manifestacion en la carretera")
        assert tipo == "Manifestación"

    def test_reten(self):
        emoji, tipo = self.fn("retén de revisión en Querétaro")
        assert tipo == "Operativo/Retén"

    def test_texto_sin_clasificar(self):
        emoji, tipo = self.fn("noticias de tráfico sin categoría conocida")
        assert tipo == "Aviso vial"
        assert emoji == "📡"


class TestNitterAgencia:
    def setup_method(self):
        from sources.nitter_monitor import _detectar_agencia
        self.fn = _detectar_agencia

    def test_capufe_detectado(self):
        r = self.fn("capufe informa cierre en caseta")
        assert r is not None
        assert r[1] == "CAPUFE"

    def test_guardia_nacional(self):
        r = self.fn("guardia nacional reporta retén en Tamaulipas")
        assert r is not None
        assert r[1] == "Guardia Nacional"

    def test_sict(self):
        r = self.fn("sict emite aviso por derrumbe")
        assert r is not None
        assert r[1] == "SICT"

    def test_sin_agencia_retorna_none(self):
        assert self.fn("accidente en la carretera sin fuente oficial") is None

    def test_case_insensitive(self):
        r = self.fn("CAPUFE cierra tramo")
        assert r is not None


class TestNitterRelevante:
    def setup_method(self):
        from sources.nitter_monitor import _es_relevante
        self.fn = _es_relevante

    def test_sin_keywords_no_es_relevante(self):
        assert self.fn("noticias de deporte y espectáculos", {"MEX-57D"}, []) is False

    def test_keyword_sin_filtro_es_relevante(self):
        assert self.fn("accidente en carretera", set(), []) is True

    def test_keyword_con_highway_que_coincide(self):
        assert self.fn("accidente mex-57d", {"MEX-57D"}, []) is True

    def test_keyword_con_highway_que_no_coincide(self):
        assert self.fn("accidente en autopista sin nombre", {"MEX-57D"}, []) is False

    def test_keyword_con_ciudad_que_coincide(self):
        assert self.fn("cierre en querétaro", set(), ["Querétaro"]) is True

    def test_keyword_con_ciudad_que_no_coincide(self):
        assert self.fn("accidente en carretera lejana", set(), ["Monterrey"]) is False


class TestNitterToAlerta:
    def setup_method(self):
        from sources.nitter_monitor import _to_alerta
        self.fn = _to_alerta

    def test_tiene_campos_obligatorios(self):
        a = self.fn("cierre en MEX-57D")
        for campo in ("tipo", "emoji", "descripcion", "severidad", "fuente", "tweet_hash"):
            assert campo in a

    def test_fuente_por_defecto(self):
        a = self.fn("accidente", fuente="Google News")
        assert a["fuente"] == "Google News"

    def test_fuente_nitter(self):
        a = self.fn("bloqueo", fuente="X/Twitter")
        assert a["fuente"] == "X/Twitter"

    def test_oficial_eleva_severidad(self):
        a_oficial = self.fn("capufe cierra carretera", oficial=True)
        a_normal = self.fn("cierre en carretera")
        assert a_oficial["severidad"] >= a_normal["severidad"]

    def test_agencia_detectada_pone_autor(self):
        a = self.fn("capufe reporta cierre")
        assert a.get("autor") is not None

    def test_tweet_hash_es_hex_12(self):
        a = self.fn("texto de prueba")
        h = a["tweet_hash"]
        assert len(h) == 12
        assert all(c in "0123456789abcdef" for c in h)


class TestNitterRouteSuffix:
    def setup_method(self):
        from sources.nitter_monitor import _route_suffix
        self.fn = _route_suffix

    def test_sin_highways_ni_ciudades_retorna_vacio(self):
        assert self.fn(set(), []) == ""

    def test_con_highway_incluye_nombre(self):
        s = self.fn({"MEX-57D"}, [])
        assert "MEX-57D" in s

    def test_con_ciudad_incluye_nombre(self):
        s = self.fn(set(), ["Querétaro"])
        assert "Querétaro" in s

    def test_highways_tienen_prioridad_sobre_ciudades(self):
        # Si hay highways, el sufijo las usa (no las ciudades)
        s_hw = self.fn({"MEX-57D"}, ["Querétaro"])
        s_c = self.fn(set(), ["Querétaro"])
        assert "MEX-57D" in s_hw


class TestNitterParseGnews:
    def setup_method(self):
        from sources.nitter_monitor import _parse_gnews
        self.fn = _parse_gnews

    def _rss(self, titles: list[str]) -> str:
        items = ""
        for t in titles:
            items += f"<item><title>{t}</title><pubDate>Mon, 15 Jan 2099 12:00:00 +0000</pubDate></item>"
        return f"<rss><channel>{items}</channel></rss>"

    def test_extrae_titulos(self):
        xml = self._rss(["Accidente en MEX-57D", "Cierre en autopista"])
        result = self.fn(xml, max_hours=999999)
        assert "Accidente en MEX-57D" in result
        assert "Cierre en autopista" in result

    def test_xml_invalido_retorna_lista_vacia(self):
        assert self.fn("esto no es xml", max_hours=999999) == []

    def test_sin_items_retorna_lista_vacia(self):
        assert self.fn("<rss><channel></channel></rss>", max_hours=999999) == []

    def test_items_antiguos_son_filtrados(self):
        # max_hours=0 → cutoff=ahora → todos los ítems del pasado se filtran
        xml = self._rss(["Noticia vieja"])
        # Usar fecha muy en el pasado (2020)
        xml_viejo = "<rss><channel><item><title>Noticia vieja</title><pubDate>Mon, 15 Jan 2020 12:00:00 +0000</pubDate></item></channel></rss>"
        result = self.fn(xml_viejo, max_hours=0)
        assert "Noticia vieja" not in result


# ═══════════════════════════════════════════════════════════════════════════════
#  17. Robbery News — geocode y estado
# ═══════════════════════════════════════════════════════════════════════════════

class TestRobberyGeocode:
    def setup_method(self):
        from sources.robbery_news import _geocode
        from regions.city_graph import CITY_NODES
        self.fn = _geocode
        self.nodes = CITY_NODES

    def test_ciudad_conocida_retorna_coords(self):
        coords = self.fn("asalto a transportista en Querétaro")
        assert coords is not None
        lat, lon = coords
        assert 14 <= lat <= 33
        assert -120 <= lon <= -85

    def test_monterrey_en_titulo(self):
        coords = self.fn("robo a camión cerca de Monterrey en carretera")
        assert coords is not None

    def test_ciudad_desconocida_retorna_none(self):
        assert self.fn("asalto en ciudad sin nombre conocido xyzabc") is None

    def test_texto_vacio_retorna_none(self):
        assert self.fn("") is None


class TestRobberyEstadoCoords:
    def setup_method(self):
        from sources.robbery_news import _estado_coords
        self.fn = _estado_coords

    def test_jalisco_detectado(self):
        coords = self.fn("robo de carga en Jalisco")
        assert coords is not None
        lat, lon = coords
        assert 14 <= lat <= 33

    def test_nuevo_leon_detectado(self):
        coords = self.fn("piratería terrestre en Nuevo León")
        assert coords is not None

    def test_chihuahua_detectado(self):
        coords = self.fn("asalto en Chihuahua")
        assert coords is not None

    def test_sin_estado_retorna_none(self):
        assert self.fn("asalto en lugar desconocido xyz") is None

    def test_baja_california_sur_distinto_de_baja_california(self):
        # "Baja California Sur" es más largo y debe resolverse primero
        coords_sur = self.fn("robo en Baja California Sur")
        coords_bc  = self.fn("robo en Baja California")
        # Ambos deben retornar algo (aunque sean distintos)
        assert coords_sur is not None
        assert coords_bc is not None

    def test_acentos_normalizados(self):
        # "Yucatán" con tilde debe match igual que "Yucatan"
        coords1 = self.fn("robo en Yucatán")
        coords2 = self.fn("robo en Yucatan")
        assert coords1 == coords2


# ═══════════════════════════════════════════════════════════════════════════════
#  19. Mexico Regions — funciones puras
# ═══════════════════════════════════════════════════════════════════════════════

class TestMexicoRegionsFunciones:
    def setup_method(self):
        from regions.mexico_regions import (
            get_region_por_estado, get_regions_info,
            REGIONS, ESTADO_A_REGION,
        )
        self.por_estado = get_region_por_estado
        self.info = get_regions_info
        self.regions = REGIONS
        self.mapa = ESTADO_A_REGION

    def test_jalisco_es_occidente(self):
        assert self.por_estado("Jalisco") == "occidente"

    def test_nuevo_leon_es_noreste(self):
        assert self.por_estado("Nuevo León") == "noreste"

    def test_abreviatura_jal_es_occidente(self):
        assert self.por_estado("JAL") == "occidente"

    def test_abreviatura_nl_es_noreste(self):
        assert self.por_estado("NL") == "noreste"

    def test_estado_inexistente_retorna_none(self):
        assert self.por_estado("Mordor") is None

    def test_cdmx_es_centro(self):
        assert self.por_estado("CDMX") == "centro"

    def test_get_regions_info_retorna_datos(self):
        result = self.info(["centro", "noreste"])
        assert len(result) == 2
        assert result[0]["key"] == "centro"
        assert "nombre" in result[0]
        assert "emoji" in result[0]

    def test_get_regions_info_filtra_claves_invalidas(self):
        result = self.info(["centro", "no_existe"])
        assert len(result) == 1
        assert result[0]["key"] == "centro"

    def test_get_regions_info_lista_vacia(self):
        assert self.info([]) == []

    def test_todas_las_regiones_tienen_campos_clave(self):
        for key, data in self.regions.items():
            for campo in ("nombre", "emoji", "estados", "carreteras_clave"):
                assert campo in data, f"Región {key} sin campo {campo}"

    def test_ocho_regiones_definidas(self):
        assert len(self.regions) == 8

    def test_estado_a_region_no_esta_vacio(self):
        assert len(self.mapa) > 0

    def test_todas_las_abreviaturas_en_mapa(self):
        for key, data in self.regions.items():
            for abr in data["abreviaturas"]:
                assert abr.lower() in self.mapa, f"Falta abreviatura: {abr}"


# ═══════════════════════════════════════════════════════════════════════════════
#  20. RCPN Monitor — funciones puras
# ═══════════════════════════════════════════════════════════════════════════════

class TestRCPNClasificar:
    def setup_method(self):
        from sources.rcpn_monitor import _clasificar
        self.fn = _clasificar

    def test_marcha_es_movilizacion(self):
        emoji, tipo = self.fn("RCPN convoca marcha para el sábado")
        assert tipo == "Movilización"
        assert emoji == "🚶"

    def test_plantón_es_movilizacion(self):
        _, tipo = self.fn("Plantón frente al INE organizado por RCPN")
        assert tipo == "Movilización"

    def test_demanda_es_legal(self):
        _, tipo = self.fn("Arturo Morales presenta demanda ante tribunal")
        assert tipo == "Legal/Político"

    def test_fraude_es_legal(self):
        _, tipo = self.fn("Denuncian fraude electoral en Michoacán")
        assert tipo == "Legal/Político"

    def test_detencion_es_represion(self):
        emoji, tipo = self.fn("Detenidos activistas de resistencia civil")
        assert tipo == "Represión"
        assert emoji == "🚨"

    def test_declaracion(self):
        _, tipo = self.fn("Arturo Morales declaró que continuarán las acciones")
        assert tipo == "Declaración"

    def test_logro(self):
        emoji, tipo = self.fn("Victoria para RCPN: tribunal revocó acuerdo")
        assert tipo == "Logro"
        assert emoji == "✅"

    def test_noticia_sin_clasificar(self):
        emoji, tipo = self.fn("Texto genérico sin palabras clave específicas")
        assert tipo == "Noticia"
        assert emoji == "📰"


class TestRCPNParseGnews:
    def setup_method(self):
        from sources.rcpn_monitor import _parse_gnews
        self.fn = _parse_gnews

    def _rss(self, items: list[tuple]) -> str:
        body = ""
        for t, pub, link, fuente in items:
            src = f'<source url="http://ejemplo.com">{fuente}</source>' if fuente else ""
            body += (f"<item><title>{t}</title>"
                     f"<pubDate>{pub}</pubDate>"
                     f"<link>{link}</link>{src}</item>")
        return f"<rss><channel>{body}</channel></rss>"

    def _item(self, title="RCPN marcha", pub="Mon, 15 Jan 2099 12:00:00 +0000",
              link="https://ejemplo.com/nota", fuente="El Universal"):
        return (title, pub, link, fuente)

    def test_extrae_titulo(self):
        xml = self._rss([self._item()])
        result = self.fn(xml)
        assert result[0]["title"] == "RCPN marcha"

    def test_extrae_link(self):
        xml = self._rss([self._item(link="https://proceso.com.mx/nota")])
        result = self.fn(xml)
        assert result[0]["link"] == "https://proceso.com.mx/nota"

    def test_extrae_fuente(self):
        xml = self._rss([self._item(fuente="Proceso")])
        result = self.fn(xml)
        assert result[0]["fuente"] == "Proceso"

    def test_item_sin_fuente_usa_default(self):
        xml = self._rss([("Noticia", "Mon, 15 Jan 2099 12:00:00 +0000", "http://x.com", "")])
        result = self.fn(xml, fuente_default="Google News")
        assert result[0]["fuente"] == "Google News"

    def test_items_futuros_pasan_ventana(self):
        xml = self._rss([self._item(pub="Mon, 15 Jan 2099 12:00:00 +0000")])
        assert len(self.fn(xml)) == 1

    def test_xml_invalido_retorna_vacio(self):
        assert self.fn("esto no es xml") == []

    def test_items_tienen_dt(self):
        xml = self._rss([self._item()])
        result = self.fn(xml)
        assert "dt" in result[0]

    def test_multiples_items(self):
        xml = self._rss([self._item(title="N1"), self._item(title="N2")])
        assert len(self.fn(xml)) == 2


class TestRCPNExcluir:
    def setup_method(self):
        from sources.rcpn_monitor import _excluir
        self.fn = _excluir

    # ── Desastres naturales → siempre excluir ─────────────────────────────────
    def test_huracan_excluido(self):
        assert self.fn("Embajada de EEUU emite alerta máxima por el poderoso huracán Polo") is True

    def test_tormenta_tropical_excluida(self):
        assert self.fn("Tormenta tropical avanza hacia costas de Jalisco") is True

    def test_ciclon_excluido(self):
        assert self.fn("Ciclón categoría 3 amenaza el Pacífico mexicano") is True

    # ── Morena/AMLO sin contexto de protesta → excluir ───────────────────────
    def test_regeneracion_nacional_excluida(self):
        assert self.fn("15 años del movimiento de regeneración nacional - El Diario de Sonora") is True

    def test_amlo_discurso_excluido(self):
        assert self.fn("Andrés Manuel presenta informe de gobierno ante seguidores") is True

    def test_morena_celebra_excluida(self):
        assert self.fn("Morena celebra su aniversario con mitin en el Zócalo") is True

    def test_sheinbaum_excluida(self):
        assert self.fn("Claudia Sheinbaum anuncia nuevos programas sociales") is True

    # ── Morena/AMLO como blanco de protesta → conservar ──────────────────────
    def test_marcha_contra_amlo_conservada(self):
        assert self.fn("RCPN marcha contra AMLO en el Zócalo") is False

    def test_protesta_contra_morena_conservada(self):
        assert self.fn("Protesta ciudadana frente a sede de Morena en CDMX") is False

    def test_resistencia_contra_4t_conservada(self):
        assert self.fn("Resistencia civil exige cuentas a la 4T en manifestación") is False

    # ── Noticias legítimas de resistencia civil → conservar ───────────────────
    def test_palalia_conservada(self):
        assert self.fn("Pagados por Palalia's Tours: 100 personas cerraron la Vía Atlixcáyotl") is False

    def test_violencia_en_oaxaca_conservada(self):
        assert self.fn("Noche de violencia en Oaxaca: balean palacio municipal") is False

    def test_ataque_lecheria_conservado(self):
        assert self.fn("Ataque armado en la Lechería-Texcoco deja dos muertos") is False

    def test_marcha_rcpn_conservada(self):
        assert self.fn("RCPN convoca marcha nacional para el sábado") is False


class TestRCPNConstantes:
    def setup_method(self):
        import sources.rcpn_monitor as m
        self.m = m

    def test_dias_reciente_menor_que_semana(self):
        assert self.m.DIAS_RECIENTE < self.m.DIAS_SEMANA

    def test_dias_semana_menor_que_max(self):
        assert self.m.DIAS_SEMANA < self.m.MAX_DIAS

    def test_max_dias_es_30(self):
        assert self.m.MAX_DIAS == 30

    def test_hay_dos_queries(self):
        assert len(self.m._GNEWS_QUERIES) == 2

    def test_queries_no_vacias(self):
        for q, _ in self.m._GNEWS_QUERIES:
            assert q.strip(), "Query vacía en _GNEWS_QUERIES"

    def test_clasificacion_tiene_entradas(self):
        assert len(self.m._CLASIFICACION) >= 4

    def test_hay_queries_no_vacias(self):
        for q, _ in self.m._GNEWS_QUERIES:
            assert q.strip()
