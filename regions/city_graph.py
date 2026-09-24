"""
Grafo de ciudades-hub para ruteo preciso de transporte de carga.

Reemplaza el grafo de 8 regiones con ~50 nodos de ciudades clave.
Cada arista lleva el número de carretera federal exacto que las conecta,
lo que permite filtrar incidentes TomTom a la MEX-XX específica de la ruta.

Algoritmo:
  resolve_city(name)       → city_key  (normaliza + alias lookup)
  bfs_city_path(ori, dst)  → [city_key, ...]
  get_route_segments(path) → [(city_key, lat, lon, {highways}), ...]
"""

import unicodedata
import heapq
from collections import deque


def _norm(text: str) -> str:
    """'Querétaro' → 'queretaro'"""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


# ── Coordenadas de cada ciudad-hub ─────────────────────────────────────────
CITY_NODES: dict[str, tuple[float, float]] = {
    # Centro / Valle de México
    "cdmx":              (19.43,  -99.13),
    "puebla":            (19.04,  -98.20),
    "cuernavaca":        (18.92,  -99.23),
    "pachuca":           (20.12,  -98.73),
    "toluca":            (19.29,  -99.66),
    "xalapa":            (19.54,  -96.93),
    # Golfo / Veracruz
    "veracruz":          (19.20,  -96.13),
    "coatzacoalcos":     (18.14,  -94.44),
    "tampico":           (22.25,  -97.87),
    "ciudad_valles":     (21.99,  -99.01),
    # Sureste
    "villahermosa":      (17.99,  -92.93),
    "campeche":          (19.85,  -90.52),
    "cd_carmen":         (18.65,  -91.82),
    "merida":            (20.97,  -89.62),
    "cancun":            (21.16,  -86.85),
    "oaxaca":            (17.06,  -96.72),
    "tapachula":         (14.90,  -92.27),
    "tuxtla":            (16.75,  -93.11),
    # Bajío / Centro-Norte
    "queretaro":         (20.60, -100.39),
    "leon":              (21.12, -101.68),
    "aguascalientes":    (21.88, -102.30),
    "zacatecas":         (22.77, -102.58),
    "san_luis_potosi":   (22.15, -100.98),
    "matehuala":         (23.65, -100.63),
    # Occidente
    "guadalajara":       (20.68, -103.35),
    "tepic":             (21.50, -104.90),
    "colima":            (19.24, -103.72),
    "morelia":           (19.70, -101.19),
    "lazaro_cardenas":   (17.96, -102.17),
    "manzanillo":        (19.05, -104.32),
    # Noreste
    "monterrey":         (25.68, -100.32),
    "saltillo":          (25.42, -101.00),
    "torreon":           (25.54, -103.45),
    "nuevo_laredo":      (27.47,  -99.52),
    "reynosa":           (26.09,  -98.28),
    "matamoros":         (25.87,  -97.50),
    "piedras_negras":    (28.70, -100.52),
    "monclova":          (26.91, -101.42),
    # Norte
    "durango":           (24.02, -104.66),
    "chihuahua":         (28.63, -106.07),
    "ciudad_juarez":     (31.74, -106.49),
    "parral":            (26.93, -105.67),
    "cuauhtemoc":        (28.41, -106.87),
    "nuevo_casas_grandes":(30.41,-107.91),
    # Noroeste
    "hermosillo":        (29.07, -110.97),
    "culiacan":          (24.80, -107.40),
    "mazatlan":          (23.24, -106.41),
    "los_mochis":        (25.78, -109.02),
    "nogales":           (31.32, -110.93),
    "mexicali":          (32.62, -115.45),
    "tijuana":           (32.53, -117.03),
    "la_paz":            (24.14, -110.31),
    "agua_prieta":       (31.33, -109.56),
    "acapulco":          (16.86,  -99.88),
}

# ── Nombre de display por ciudad-hub ───────────────────────────────────────
CITY_LABELS: dict[str, str] = {
    "cdmx": "CDMX", "puebla": "Puebla", "cuernavaca": "Cuernavaca",
    "pachuca": "Pachuca", "toluca": "Toluca", "xalapa": "Xalapa",
    "veracruz": "Veracruz", "coatzacoalcos": "Coatzacoalcos",
    "tampico": "Tampico", "ciudad_valles": "Ciudad Valles",
    "villahermosa": "Villahermosa", "campeche": "Campeche",
    "cd_carmen": "Ciudad del Carmen", "merida": "Mérida",
    "cancun": "Cancún", "oaxaca": "Oaxaca", "tapachula": "Tapachula",
    "tuxtla": "Tuxtla Gutiérrez",
    "queretaro": "Querétaro", "leon": "León",
    "aguascalientes": "Aguascalientes", "zacatecas": "Zacatecas",
    "san_luis_potosi": "San Luis Potosí", "matehuala": "Matehuala",
    "guadalajara": "Guadalajara", "tepic": "Tepic",
    "colima": "Colima", "morelia": "Morelia",
    "lazaro_cardenas": "Lázaro Cárdenas", "manzanillo": "Manzanillo",
    "monterrey": "Monterrey", "saltillo": "Saltillo",
    "torreon": "Torreón", "nuevo_laredo": "Nuevo Laredo",
    "reynosa": "Reynosa", "matamoros": "Matamoros",
    "piedras_negras": "Piedras Negras", "monclova": "Monclova",
    "durango": "Durango", "chihuahua": "Chihuahua",
    "ciudad_juarez": "Ciudad Juárez", "parral": "Parral",
    "cuauhtemoc": "Cuauhtémoc", "nuevo_casas_grandes": "Nuevo Casas Grandes",
    "hermosillo": "Hermosillo", "culiacan": "Culiacán",
    "mazatlan": "Mazatlán", "los_mochis": "Los Mochis",
    "nogales": "Nogales", "mexicali": "Mexicali",
    "tijuana": "Tijuana", "la_paz": "La Paz",
    "agua_prieta": "Agua Prieta", "acapulco": "Acapulco",
}

# ── Grafo de aristas dirigidas ciudad→ciudad con highway ──────────────────
# Cada entrada: "ciudad_origen": {"ciudad_destino": "MEX-XX"}
# Se define en ambas direcciones para que el BFS funcione.
CITY_EDGES: dict[str, dict[str, str]] = {
    # ── CDMX ──────────────────────────────────────────────────────
    "cdmx": {
        "queretaro":      "MEX-57D",   # norte: eje San Luis-Monterrey
        "toluca":         "MEX-15D",   # oeste: eje Guadalajara-Pacífico
        "puebla":         "MEX-150D",  # este: eje Veracruz
        "cuernavaca":     "MEX-95D",   # sur: eje Acapulco
        "pachuca":        "MEX-85D",   # noreste: eje Tampico
    },
    # ── Eje CDMX-QRO-MTY (MEX-57D/57) ────────────────────────────
    "queretaro": {
        "cdmx":           "MEX-57D",
        "san_luis_potosi":"MEX-57",
        "leon":           "MEX-45D",   # bifurcación hacia GDL
    },
    "san_luis_potosi": {
        "queretaro":      "MEX-57",
        "matehuala":      "MEX-57",
        "zacatecas":      "MEX-49",    # directo a ZAC/norte
        "ciudad_valles":  "MEX-70",    # a Tampico
    },
    "matehuala": {
        "san_luis_potosi":"MEX-57",
        "monterrey":      "MEX-57",
    },
    # ── Eje Bajío (MEX-45D) QRO-GDL ───────────────────────────────
    "leon": {
        "queretaro":      "MEX-45D",
        "guadalajara":    "MEX-80",
        "aguascalientes": "MEX-45",
    },
    # ── Noreste: Monterrey y sus salidas ──────────────────────────
    "monterrey": {
        "matehuala":      "MEX-57",
        "saltillo":       "MEX-40D",
        "nuevo_laredo":   "MEX-85",
        "reynosa":        "MEX-40",
        "matamoros":      "MEX-40",
        "tampico":        "MEX-85",
    },
    "saltillo": {
        "monterrey":      "MEX-40D",
        "torreon":        "MEX-40",
        "piedras_negras": "MEX-57",    # vía Monclova
        "monclova":       "MEX-57",
    },
    "monclova": {
        "saltillo":       "MEX-57",
        "piedras_negras": "MEX-57",
        "torreon":        "MEX-53",
    },
    "torreon": {
        "saltillo":       "MEX-40",
        "durango":        "MEX-40",
        "zacatecas":      "MEX-54",
        "monclova":       "MEX-53",
    },
    "nuevo_laredo": {
        "monterrey":      "MEX-85",
        "piedras_negras": "MEX-2",     # frontera
    },
    "reynosa": {
        "monterrey":      "MEX-40",
        "matamoros":      "MEX-101",
    },
    "matamoros": {
        "monterrey":      "MEX-40",
        "reynosa":        "MEX-101",
        "tampico":        "MEX-180",
    },
    "piedras_negras": {
        "saltillo":       "MEX-57",
        "monclova":       "MEX-57",
        "nuevo_laredo":   "MEX-2",
    },
    # ── Eje Central Norte (MEX-45/49) ZAC-DGO-CHIH-JUA ───────────
    "zacatecas": {
        "san_luis_potosi":"MEX-49",
        "aguascalientes": "MEX-45",
        "durango":        "MEX-45",
        "torreon":        "MEX-54",
    },
    "aguascalientes": {
        "leon":           "MEX-45",
        "zacatecas":      "MEX-45",
        "guadalajara":    "MEX-45",
    },
    "durango": {
        "zacatecas":      "MEX-45",
        "torreon":        "MEX-40",
        "chihuahua":      "MEX-45",
        "mazatlan":       "MEX-40",    # espinazo del diablo
        "parral":         "MEX-45",
    },
    "chihuahua": {
        "durango":        "MEX-45",
        "ciudad_juarez":  "MEX-45",
        "hermosillo":     "MEX-16",
        "cuauhtemoc":     "MEX-16",
        "parral":         "MEX-45",
        "nuevo_casas_grandes": "MEX-10",
    },
    "ciudad_juarez": {
        "chihuahua":      "MEX-45",
        "agua_prieta":    "MEX-2",
    },
    "parral": {
        "chihuahua":      "MEX-45",
        "durango":        "MEX-45",
    },
    "cuauhtemoc": {
        "chihuahua":      "MEX-16",
        "nuevo_casas_grandes": "MEX-16",
    },
    "nuevo_casas_grandes": {
        "cuauhtemoc":     "MEX-16",
        "chihuahua":      "MEX-10",
    },
    # ── Noroeste: Hermosillo y corredor Pacífico ───────────────────
    "hermosillo": {
        "chihuahua":      "MEX-16",
        "culiacan":       "MEX-15",
        "nogales":        "MEX-15",
        "agua_prieta":    "MEX-2",
        "mexicali":       "MEX-2",    # vía San Luis Río Colorado
    },
    "nogales": {
        "hermosillo":     "MEX-15",
    },
    "agua_prieta": {
        "hermosillo":     "MEX-2",
        "ciudad_juarez":  "MEX-2",
    },
    "culiacan": {
        "hermosillo":     "MEX-15",
        "mazatlan":       "MEX-15",
        "los_mochis":     "MEX-15",
    },
    "los_mochis": {
        "culiacan":       "MEX-15",
        "hermosillo":     "MEX-15",
        "la_paz":         "MEX-1",    # transbordador Topolobampo-La Paz
    },
    "mazatlan": {
        "culiacan":       "MEX-15",
        "tepic":          "MEX-15",
        "durango":        "MEX-40",
    },
    "mexicali": {
        "tijuana":        "MEX-2",
        "hermosillo":     "MEX-8",
    },
    "tijuana": {
        "mexicali":       "MEX-2",
        "ensenada":       "MEX-1",
    },
    "la_paz": {
        "los_mochis":     "MEX-1",    # transbordador / MEX-1
    },
    # ── Eje Pacífico (MEX-15D/15) CDMX-GDL-Pacífico ──────────────
    "toluca": {
        "cdmx":           "MEX-15D",
        "morelia":        "MEX-15",
    },
    "guadalajara": {
        "leon":           "MEX-80",
        "aguascalientes": "MEX-45",
        "tepic":          "MEX-15D",
        "morelia":        "MEX-15",
        "colima":         "MEX-54",
        "manzanillo":     "MEX-54",
    },
    "tepic": {
        "guadalajara":    "MEX-15D",
        "mazatlan":       "MEX-15",
    },
    "morelia": {
        "toluca":         "MEX-15",
        "guadalajara":    "MEX-15",
        "lazaro_cardenas":"MEX-37",
        "puebla":         "MEX-15",    # vía Maravatío-Atlacomulco
    },
    "colima": {
        "guadalajara":    "MEX-54",
        "manzanillo":     "MEX-200",
        "lazaro_cardenas":"MEX-200",
    },
    "manzanillo": {
        "guadalajara":    "MEX-54",
        "lazaro_cardenas":"MEX-200",
        "colima":         "MEX-200",
    },
    "lazaro_cardenas": {
        "morelia":        "MEX-37",
        "manzanillo":     "MEX-200",
        "colima":         "MEX-200",
    },
    # ── Eje Puebla-Veracruz (MEX-150D) ────────────────────────────
    "puebla": {
        "cdmx":           "MEX-150D",
        "veracruz":       "MEX-150D",
        "oaxaca":         "MEX-190",
    },
    "veracruz": {
        "puebla":         "MEX-150D",
        "xalapa":         "MEX-140",
        "tampico":        "MEX-180",
        "coatzacoalcos":  "MEX-180D",
    },
    "xalapa": {
        "veracruz":       "MEX-140",
        "puebla":         "MEX-140",
    },
    # ── Eje Golfo (MEX-180/85) ─────────────────────────────────────
    "tampico": {
        "monterrey":      "MEX-85",
        "ciudad_valles":  "MEX-70",
        "veracruz":       "MEX-180",
        "matamoros":      "MEX-180",
        # nota: tampico→pachuca se hace vía ciudad_valles, sin arista directa
    },
    "ciudad_valles": {
        "tampico":        "MEX-70",
        "san_luis_potosi":"MEX-70",
    },
    # ── Eje Sureste (MEX-180/186) VH-Campeche-Mérida ──────────────
    "coatzacoalcos": {
        "veracruz":       "MEX-180D",
        "villahermosa":   "MEX-180",
        "oaxaca":         "MEX-185",
    },
    "villahermosa": {
        "coatzacoalcos":  "MEX-180",
        "campeche":       "MEX-186",
        "cd_carmen":      "MEX-180",
    },
    "campeche": {
        "villahermosa":   "MEX-186",
        "merida":         "MEX-180",
        "cd_carmen":      "MEX-261",
    },
    "cd_carmen": {
        "villahermosa":   "MEX-180",
        "campeche":       "MEX-261",
    },
    "merida": {
        "campeche":       "MEX-180",
        "cancun":         "MEX-180D",
    },
    "cancun": {
        "merida":         "MEX-180D",
    },
    # ── Oaxaca / Chiapas ──────────────────────────────────────────
    "oaxaca": {
        "puebla":         "MEX-190",
        "coatzacoalcos":  "MEX-185",
        "tapachula":      "MEX-190",
        "tuxtla":         "MEX-190",
    },
    "tuxtla": {
        "oaxaca":         "MEX-190",
        "tapachula":      "MEX-190",
        "villahermosa":   "MEX-195",
    },
    "tapachula": {
        "tuxtla":         "MEX-190",
        "oaxaca":         "MEX-190",
    },
    # ── Sur ───────────────────────────────────────────────────────
    "cuernavaca": {
        "cdmx":           "MEX-95D",
        "acapulco":       "MEX-95D",
        "puebla":         "MEX-160",
    },
    "acapulco": {
        "cuernavaca":     "MEX-95D",
    },
    "pachuca": {
        "cdmx":           "MEX-85D",
        "ciudad_valles":  "MEX-85",   # Pachuca→Tampico va vía Ciudad Valles, sin arista directa
    },
}

# ── Aliases: nombre normalizado → city_key ─────────────────────────────────
# Incluye variantes, apodos, municipios del área metropolitana
_ALIASES_RAW: dict[str, str] = {
    # CDMX y área metro norte (MEX-57D)
    "cdmx": "cdmx", "ciudad de mexico": "cdmx", "mexico": "cdmx",
    "df": "cdmx", "ciudad mexico": "cdmx",
    "tepozotlan": "cdmx", "tepotzotlan": "cdmx",
    "tepotzotlan mexico": "cdmx", "tepozotlan mexico": "cdmx",
    "cuautitlan": "cdmx", "cuautitlan izcalli": "cdmx",
    "huehuetoca": "cdmx", "tultitlan": "cdmx", "tultepec": "cdmx",
    "ecatepec": "cdmx", "naucalpan": "cdmx", "tlalnepantla": "cdmx",
    "nezahualcoyotl": "cdmx", "ixtapaluca": "cdmx", "chalco": "cdmx",
    "atizapan": "cdmx", "coacalco": "cdmx", "texcoco": "cdmx",
    # Puebla
    "puebla": "puebla", "cholula": "puebla", "atlixco": "puebla",
    "tehuacan": "puebla", "amozoc": "puebla", "huejotzingo": "puebla",
    "san martin texmelucan": "puebla",
    # Cuernavaca
    "cuernavaca": "cuernavaca", "cuautla": "cuernavaca",
    "jiutepec": "cuernavaca", "temixco": "cuernavaca",
    # Acapulco
    "acapulco": "acapulco", "zihuatanejo": "acapulco", "ixtapa": "acapulco",
    # Pachuca
    "pachuca": "pachuca", "tizayuca": "pachuca", "tulancingo": "pachuca",
    "apan": "pachuca",
    # Toluca
    "toluca": "toluca", "metepec": "toluca", "lerma": "toluca",
    "atlacomulco": "toluca",
    # Xalapa
    "xalapa": "xalapa", "jalapa": "xalapa",
    # Veracruz
    "veracruz": "veracruz", "boca del rio": "veracruz",
    "alvarado": "veracruz",
    # Coatzacoalcos
    "coatzacoalcos": "coatzacoalcos", "minatitlan": "coatzacoalcos",
    "cosoleacaque": "coatzacoalcos", "acayucan": "coatzacoalcos",
    # Tampico
    "tampico": "tampico", "altamira": "tampico",
    "ciudad madero": "tampico", "cd madero": "tampico",
    # Ciudad Valles
    "ciudad valles": "ciudad_valles", "cd valles": "ciudad_valles",
    "valles": "ciudad_valles", "tamazunchale": "ciudad_valles",
    # Villahermosa
    "villahermosa": "villahermosa", "cardenas tab": "villahermosa",
    "comalcalco": "villahermosa",
    # Campeche
    "campeche": "campeche", "champoton": "campeche",
    "hopelchen": "campeche", "escarcega": "campeche",
    # Ciudad del Carmen
    "ciudad del carmen": "cd_carmen", "cd del carmen": "cd_carmen",
    "carmen": "cd_carmen",
    # Mérida
    "merida": "merida", "progreso": "merida", "izamal": "merida",
    "ticul": "merida",
    # Cancún
    "cancun": "cancun", "playa del carmen": "cancun",
    "tulum": "cancun", "cozumel": "cancun", "chetumal": "cancun",
    "bacalar": "cancun", "valladolid": "cancun",
    # Oaxaca
    "oaxaca": "oaxaca", "salina cruz": "oaxaca", "huatulco": "oaxaca",
    "juchitan": "oaxaca", "tehuantepec": "oaxaca",
    # Tuxtla
    "tuxtla": "tuxtla", "tuxtla gutierrez": "tuxtla",
    "san cristobal": "tuxtla", "san cristobal de las casas": "tuxtla",
    "comitan": "tuxtla", "ocozocoautla": "tuxtla",
    # Tapachula
    "tapachula": "tapachula", "huixtla": "tapachula",
    "tonala chis": "tapachula",
    # Querétaro
    "queretaro": "queretaro", "qro": "queretaro",
    "san juan del rio": "queretaro", "tequisquiapan": "queretaro",
    # León
    "leon": "leon", "irapuato": "leon", "salamanca": "leon",
    "silao": "leon", "celaya": "leon", "guanajuato": "leon",
    "acambaro": "leon", "cortazar": "leon",
    # Aguascalientes
    "aguascalientes": "aguascalientes", "ags": "aguascalientes",
    "rincon de romos": "aguascalientes",
    # Zacatecas
    "zacatecas": "zacatecas", "fresnillo": "zacatecas",
    "guadalupe zac": "zacatecas", "jerez": "zacatecas",
    "loreto zac": "zacatecas", "sombrerete": "zacatecas",
    # San Luis Potosí
    "san luis potosi": "san_luis_potosi", "slp": "san_luis_potosi",
    "soledad": "san_luis_potosi",
    # Matehuala
    "matehuala": "matehuala",
    # Guadalajara
    "guadalajara": "guadalajara", "zapopan": "guadalajara",
    "tlaquepaque": "guadalajara", "tonala jal": "guadalajara",
    "tlajomulco": "guadalajara", "lagos de moreno": "guadalajara",
    "tepatitlan": "guadalajara", "arandas": "guadalajara",
    "ocotlan jal": "guadalajara",
    # Tepic
    "tepic": "tepic", "compostela": "tepic",
    "ixtlan del rio": "tepic",
    # Colima
    "colima": "colima", "villa de alvarez": "colima",
    "tecoman": "colima",
    # Morelia
    "morelia": "morelia", "uruapan": "morelia",
    "zamora": "morelia", "la piedad": "morelia",
    "patzcuaro": "morelia", "zitacuaro": "morelia",
    "maravatio": "morelia", "apatzingan": "morelia",
    "jacona": "morelia",
    # Manzanillo
    "manzanillo": "manzanillo", "puerto vallarta": "tepic",
    # Lázaro Cárdenas
    "lazaro cardenas": "lazaro_cardenas",
    # Monterrey
    "monterrey": "monterrey", "san nicolas": "monterrey",
    "apodaca": "monterrey", "escobedo": "monterrey",
    "guadalupe nl": "monterrey", "garcia nl": "monterrey",
    "santa catarina nl": "monterrey", "linares": "monterrey",
    "montemorelos": "monterrey", "cadereyta nl": "monterrey",
    "san pedro garza garcia": "monterrey",
    # Saltillo
    "saltillo": "saltillo", "ramos arizpe": "saltillo",
    "parras": "saltillo", "arteaga coah": "saltillo",
    # Torreón
    "torreon": "torreon", "gomez palacio": "torreon",
    "lerdo": "torreon", "matamoros coah": "torreon",
    # Monclova
    "monclova": "monclova", "frontera coah": "monclova",
    "sabinas coah": "monclova", "nueva rosita": "monclova",
    "muzquiz": "monclova",
    # Nuevo Laredo
    "nuevo laredo": "nuevo_laredo", "laredo": "nuevo_laredo",
    # Reynosa
    "reynosa": "reynosa", "rio bravo": "reynosa",
    "valle hermoso": "reynosa",
    # Matamoros
    "matamoros": "matamoros",
    # Piedras Negras
    "piedras negras": "piedras_negras", "acuna": "piedras_negras",
    "ciudad acuna": "piedras_negras", "cd acuna": "piedras_negras",
    # Durango
    "durango": "durango", "gomez palacio dgo": "torreon",
    "lerdo dgo": "torreon",
    # Chihuahua
    "chihuahua": "chihuahua", "delicias": "chihuahua",
    # Ciudad Juárez
    "ciudad juarez": "ciudad_juarez", "juarez": "ciudad_juarez",
    "cd juarez": "ciudad_juarez",
    # Parral
    "parral": "parral", "hidalgo del parral": "parral",
    "camargo chih": "parral",
    # Cuauhtémoc
    "cuauhtemoc chih": "cuauhtemoc", "cuauhtemoc": "cuauhtemoc",
    # Nuevo Casas Grandes
    "nuevo casas grandes": "nuevo_casas_grandes",
    "casas grandes": "nuevo_casas_grandes",
    "cd juarez ojinaga": "nuevo_casas_grandes",
    # Hermosillo
    "hermosillo": "hermosillo", "guaymas": "hermosillo",
    "empalme": "hermosillo", "navojoa": "hermosillo",
    "ciudad obregon": "hermosillo", "cd obregon": "hermosillo",
    "obregon": "hermosillo",
    # Culiacán
    "culiacan": "culiacan", "guasave": "culiacan",
    "guamuchil": "culiacan", "ahome": "culiacan",
    # Los Mochis
    "los mochis": "los_mochis",
    # Mazatlán
    "mazatlan": "mazatlan", "rosario sin": "mazatlan",
    "escuinapa": "mazatlan",
    # Nogales
    "nogales": "nogales", "santa ana son": "nogales",
    "magdalena son": "nogales", "caborca": "nogales",
    # Mexicali
    "mexicali": "mexicali", "san felipe": "mexicali",
    # Tijuana
    "tijuana": "tijuana", "rosarito": "tijuana",
    "tecate": "tijuana", "ensenada": "tijuana",
    # La Paz
    "la paz": "la_paz", "cabo san lucas": "la_paz",
    "los cabos": "la_paz", "loreto bcs": "la_paz",
    # Agua Prieta
    "agua prieta": "agua_prieta",
}

# Pre-normalizar las claves del alias dict
CITY_ALIASES: dict[str, str] = {_norm(k): v for k, v in _ALIASES_RAW.items()}


def resolve_city(name: str) -> str | None:
    """
    Convierte nombre libre → city_key.
    1. Lookup directo en CITY_ALIASES (normalizado)
    2. Substring match: alias contiene la entrada o viceversa
    Retorna None si no se puede resolver.
    """
    key = _norm(name)
    if key in CITY_ALIASES:
        return CITY_ALIASES[key]
    # Substring: "tepotzotlan" encuentra "tepotzotlan mexico"
    for alias, city in CITY_ALIASES.items():
        if key in alias or alias in key:
            return city
    return None


# Distancias aproximadas en km para cada arista (orden: origen→destino).
# Permite Dijkstra y evita rutas de pocos saltos pero mayor distancia real.
# Claves en el mismo orden que CITY_EDGES.
EDGE_KM: dict[str, dict[str, int]] = {
    "cdmx":            {"queretaro": 220, "toluca": 65, "puebla": 130,
                        "cuernavaca": 85, "pachuca": 90},
    "queretaro":       {"cdmx": 220, "san_luis_potosi": 190, "leon": 150},
    "san_luis_potosi": {"queretaro": 190, "matehuala": 190, "zacatecas": 190,
                        "ciudad_valles": 200},
    "matehuala":       {"san_luis_potosi": 190, "monterrey": 210},
    "leon":            {"queretaro": 150, "guadalajara": 175, "aguascalientes": 120},
    "monterrey":       {"matehuala": 210, "saltillo": 90, "nuevo_laredo": 230,
                        "reynosa": 210, "matamoros": 260, "tampico": 280},
    "saltillo":        {"monterrey": 90, "torreon": 250,
                        "piedras_negras": 290, "monclova": 180},
    "monclova":        {"saltillo": 180, "piedras_negras": 150, "torreon": 210},
    "torreon":         {"saltillo": 250, "durango": 260, "zacatecas": 250,
                        "monclova": 210},
    "nuevo_laredo":    {"monterrey": 230, "piedras_negras": 270},
    "reynosa":         {"monterrey": 210, "matamoros": 90},
    "matamoros":       {"monterrey": 260, "reynosa": 90, "tampico": 310},
    "piedras_negras":  {"saltillo": 290, "monclova": 150, "nuevo_laredo": 270},
    "zacatecas":       {"san_luis_potosi": 190, "aguascalientes": 130,
                        "durango": 310, "torreon": 250},
    "aguascalientes":  {"leon": 120, "zacatecas": 130, "guadalajara": 220},
    "durango":         {"zacatecas": 310, "torreon": 260, "chihuahua": 540,
                        "mazatlan": 310, "parral": 230},
    "chihuahua":       {"durango": 540, "ciudad_juarez": 370, "hermosillo": 590,
                        "cuauhtemoc": 100, "parral": 220,
                        "nuevo_casas_grandes": 330},
    "ciudad_juarez":   {"chihuahua": 370, "agua_prieta": 310},
    "parral":          {"chihuahua": 220, "durango": 230},
    "cuauhtemoc":      {"chihuahua": 100, "nuevo_casas_grandes": 180},
    "nuevo_casas_grandes": {"cuauhtemoc": 180, "chihuahua": 330},
    "hermosillo":      {"chihuahua": 590, "culiacan": 420, "nogales": 280,
                        "agua_prieta": 310, "mexicali": 720},
    "nogales":         {"hermosillo": 280},
    "agua_prieta":     {"hermosillo": 310, "ciudad_juarez": 310},
    "culiacan":        {"hermosillo": 420, "mazatlan": 230, "los_mochis": 210},
    "los_mochis":      {"culiacan": 210, "hermosillo": 490, "la_paz": 600},
    "mazatlan":        {"culiacan": 230, "tepic": 310, "durango": 310},
    "mexicali":        {"tijuana": 190, "hermosillo": 720},
    "tijuana":         {"mexicali": 190},
    "la_paz":          {"los_mochis": 600},
    "toluca":          {"cdmx": 65, "morelia": 230},
    "guadalajara":     {"leon": 175, "aguascalientes": 220, "tepic": 230,
                        "morelia": 310, "colima": 190, "manzanillo": 290},
    "tepic":           {"guadalajara": 230, "mazatlan": 310},
    "morelia":         {"toluca": 230, "guadalajara": 310, "lazaro_cardenas": 340,
                        "puebla": 390},
    "colima":          {"guadalajara": 190, "manzanillo": 45,
                        "lazaro_cardenas": 280},
    "manzanillo":      {"guadalajara": 290, "lazaro_cardenas": 220,
                        "colima": 45},
    "lazaro_cardenas": {"morelia": 340, "manzanillo": 220, "colima": 280},
    "puebla":          {"cdmx": 130, "veracruz": 250, "oaxaca": 360},
    "veracruz":        {"puebla": 250, "xalapa": 110, "tampico": 320,
                        "coatzacoalcos": 300},
    "xalapa":          {"veracruz": 110, "puebla": 300},
    "tampico":         {"monterrey": 280, "ciudad_valles": 110,
                        "veracruz": 320, "matamoros": 310},
    "ciudad_valles":   {"tampico": 110, "san_luis_potosi": 200},
    "coatzacoalcos":   {"veracruz": 300, "villahermosa": 170, "oaxaca": 400},
    "villahermosa":    {"coatzacoalcos": 170, "campeche": 440, "cd_carmen": 200},
    "campeche":        {"villahermosa": 440, "merida": 190, "cd_carmen": 190},
    "cd_carmen":       {"villahermosa": 200, "campeche": 190},
    "merida":          {"campeche": 190, "cancun": 320},
    "cancun":          {"merida": 320},
    "oaxaca":          {"puebla": 360, "coatzacoalcos": 400,
                        "tapachula": 590, "tuxtla": 250},
    "tuxtla":          {"oaxaca": 250, "tapachula": 280, "villahermosa": 290},
    "tapachula":       {"tuxtla": 280, "oaxaca": 590},
    "cuernavaca":      {"cdmx": 85, "acapulco": 300, "puebla": 250},
    "acapulco":        {"cuernavaca": 300},
    # MEX-85 Pachuca→Ciudad Valles pasa por sierra Hidalguense (2 carriles, lento)
    # Se penaliza con +150 km efectivos para que Dijkstra prefiera MEX-57D
    "pachuca":         {"cdmx": 90, "ciudad_valles": 480},
}


def bfs_city_path(origin: str, dest: str) -> list[str] | None:
    """BFS mínimo sobre CITY_EDGES — solo para tests o paths cortos."""
    if origin == dest:
        return [origin]
    queue: deque[list[str]] = deque([[origin]])
    visited: set[str] = {origin}
    while queue:
        path = queue.popleft()
        for neighbor in CITY_EDGES.get(path[-1], {}):
            if neighbor == dest:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(path + [neighbor])
    return None


def dijkstra_city_path(origin: str, dest: str) -> list[str] | None:
    """
    Dijkstra sobre CITY_EDGES ponderado por EDGE_KM.
    Devuelve la ruta de menor distancia total en km.
    Para aristas sin distancia definida usa 999 (penaliza rutas desconocidas).
    """
    if origin == dest:
        return [origin]
    # heap: (dist_acumulada, ciudad_actual, path)
    heap: list[tuple[int, str, list[str]]] = [(0, origin, [origin])]
    visited: set[str] = set()
    while heap:
        dist, city, path = heapq.heappop(heap)
        if city in visited:
            continue
        visited.add(city)
        if city == dest:
            return path
        for neighbor, highway in CITY_EDGES.get(city, {}).items():
            if neighbor not in visited:
                km = EDGE_KM.get(city, {}).get(neighbor, 999)
                heapq.heappush(heap, (dist + km, neighbor, path + [neighbor]))
    return None


def get_route_segments(
    city_path: list[str],
) -> list[tuple[str, float, float, set[str]]]:
    """
    Para cada ciudad en path[1:] retorna (city_key, lat, lon, {highways}).
    highways = highway de la arista entrante ∪ highway de la arista saliente.
    Esto permite filtrar TomTom a exactamente las MEX-XX del corredor.
    """
    segments = []
    for i in range(1, len(city_path)):
        city = city_path[i]
        if city not in CITY_NODES:
            continue
        lat, lon = CITY_NODES[city]
        highways: set[str] = set()
        hw_in = CITY_EDGES.get(city_path[i - 1], {}).get(city)
        if hw_in:
            highways.add(hw_in)
        if i < len(city_path) - 1:
            hw_out = CITY_EDGES.get(city, {}).get(city_path[i + 1])
            if hw_out:
                highways.add(hw_out)
        segments.append((city, lat, lon, highways))
    return segments


def city_path_to_regions(city_path: list[str]) -> list[str]:
    """Convierte city_path a lista de regiones (para compatibilidad con monitores)."""
    from regions.mexico_regions import REGIONS

    _CITY_TO_REGION: dict[str, str] = {
        "cdmx": "centro", "puebla": "centro", "cuernavaca": "centro",
        "pachuca": "centro", "toluca": "centro", "xalapa": "golfo",
        "acapulco": "centro",
        "veracruz": "golfo", "coatzacoalcos": "golfo",
        "tampico": "noreste", "ciudad_valles": "noreste",
        "villahermosa": "golfo", "campeche": "peninsula",
        "cd_carmen": "peninsula", "merida": "peninsula",
        "cancun": "peninsula", "oaxaca": "golfo",
        "tapachula": "golfo", "tuxtla": "golfo",
        "queretaro": "centro_norte", "leon": "centro_norte",
        "aguascalientes": "centro_norte", "zacatecas": "centro_norte",
        "san_luis_potosi": "noreste", "matehuala": "noreste",
        "guadalajara": "occidente", "tepic": "occidente",
        "colima": "occidente", "morelia": "occidente",
        "lazaro_cardenas": "occidente", "manzanillo": "occidente",
        "monterrey": "noreste", "saltillo": "norte",
        "torreon": "norte", "nuevo_laredo": "noreste",
        "reynosa": "noreste", "matamoros": "noreste",
        "piedras_negras": "norte", "monclova": "norte",
        "durango": "norte", "chihuahua": "norte",
        "ciudad_juarez": "norte", "parral": "norte",
        "cuauhtemoc": "norte", "nuevo_casas_grandes": "norte",
        "hermosillo": "noroeste", "culiacan": "noroeste",
        "mazatlan": "noroeste", "los_mochis": "noroeste",
        "nogales": "noroeste", "mexicali": "noroeste",
        "tijuana": "noroeste", "la_paz": "noroeste",
        "agua_prieta": "noroeste",
    }
    regions = []
    for city in city_path:
        r = _CITY_TO_REGION.get(city)
        if r and r not in regions:
            regions.append(r)
    return regions
