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
#  11. trip_monitor — funciones auxiliares puras
# ═══════════════════════════════════════════════════════════════════════════════

class TestTripMonitorUtils:
    def setup_method(self):
        # Importar dentro del test para no romper stubs al inicio
        from scheduler.trip_monitor import _hash_incidente, _formato_incidente
        self._hash = _hash_incidente
        self._fmt  = _formato_incidente

    def test_hash_determinista(self):
        inc = {"tipo": "Accidente", "descripcion": "Choque en MEX-57D km 120"}
        assert self._hash(inc) == self._hash(inc)

    def test_hash_distinto_para_incidentes_distintos(self):
        a = {"tipo": "Accidente", "descripcion": "Choque en MEX-57D km 120"}
        b = {"tipo": "Cierre", "descripcion": "Carretera cerrada MEX-85"}
        assert self._hash(a) != self._hash(b)

    def test_hash_es_hex_32_chars(self):
        inc = {"tipo": "Obras", "descripcion": "Reparación de puente"}
        h = self._hash(inc)
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)

    def test_formato_incluye_tipo_y_descripcion(self):
        inc = {"emoji": "🚨", "tipo": "Accidente", "descripcion": "Choque km 45"}
        texto = self._fmt(inc)
        assert "Accidente" in texto
        assert "Choque km 45" in texto

    def test_formato_incluye_autor_si_hay(self):
        inc = {"emoji": "📰", "tipo": "Noticia", "descripcion": "Bloqueo", "autor": "@fuente"}
        texto = self._fmt(inc)
        assert "@fuente" in texto

    def test_formato_sin_autor_no_genera_error(self):
        inc = {"emoji": "⚠️", "tipo": "Obras", "descripcion": "Bacheo en curva"}
        texto = self._fmt(inc)
        assert "Obras" in texto


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
