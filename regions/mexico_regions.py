"""
Regiones de México para monitoreo vial de transporte de carga.
Cada región agrupa estados y tiene cuentas X/Twitter asociadas.
"""

REGIONS = {
    "noroeste": {
        "nombre": "Noroeste",
        "emoji": "🌵",
        "estados": ["Baja California", "Baja California Sur", "Sonora", "Sinaloa"],
        "abreviaturas": ["BC", "BCS", "SON", "SIN"],
        "carreteras_clave": ["MEX-2", "MEX-15", "MEX-40"],
        "cuentas_x": [
            "InfovialSonora", "TraficoSinaloa", "VialBC",
            "PCyBCSonora", "TraficoHermosillo",
        ],
        "keywords": ["sonora", "sinaloa", "baja california", "hermosillo", "culiacan",
                     "mazatlan", "tijuana", "mexicali", "accidente", "bloqueo", "carretera"],
        "casetas_capufe": ["Hermosillo", "Culiacán", "Mazatlán", "Mexicali"],
    },
    "norte": {
        "nombre": "Norte",
        "emoji": "🏜️",
        "estados": ["Chihuahua", "Durango", "Coahuila"],
        "abreviaturas": ["CHIH", "DGO", "COAH"],
        "carreteras_clave": ["MEX-45", "MEX-49", "MEX-16"],
        "cuentas_x": [
            "TraficoChihuahua", "VialDurango", "InfovialCoahuila",
            "PCChihuahua", "TraficoTorreon",
        ],
        "keywords": ["chihuahua", "durango", "coahuila", "torreon", "juarez",
                     "accidente", "bloqueo", "niebla", "granizo"],
        "casetas_capufe": ["Chihuahua", "Torreón", "Durango"],
    },
    "noreste": {
        "nombre": "Noreste",
        "emoji": "🦅",
        "estados": ["Nuevo León", "Tamaulipas", "San Luis Potosí"],
        "abreviaturas": ["NL", "TAM", "SLP"],
        "carreteras_clave": ["MEX-85", "MEX-57", "MEX-40D"],
        "cuentas_x": [
            "TraficoNL", "VialMTY", "InfovialTamaulipas",
            "PCNuevoLeon", "TraficoMonterrey", "AlertasCarreteras",
        ],
        "keywords": ["nuevo leon", "tamaulipas", "monterrey", "laredo", "reynosa",
                     "matamoros", "accidente", "bloqueo", "retén", "inspeccion"],
        "casetas_capufe": ["Monterrey", "Laredo", "Tampico", "Matehuala"],
    },
    "occidente": {
        "nombre": "Occidente",
        "emoji": "🌊",
        "estados": ["Jalisco", "Nayarit", "Colima", "Michoacán"],
        "abreviaturas": ["JAL", "NAY", "COL", "MICH"],
        "carreteras_clave": ["MEX-15D", "MEX-54", "MEX-200"],
        "cuentas_x": [
            "TraficoGDL", "VialJalisco", "InfovialOccidente",
            "PCJalisco", "TraficoGuadalajara",
        ],
        "keywords": ["jalisco", "guadalajara", "nayarit", "colima", "michoacan",
                     "morelia", "accidente", "manifestacion", "bloqueo"],
        "casetas_capufe": ["Guadalajara", "Tepic", "Morelia"],
    },
    "centro_norte": {
        "nombre": "Centro-Norte / Bajío",
        "emoji": "⛪",
        "estados": ["Zacatecas", "Aguascalientes", "Guanajuato", "Querétaro"],
        "abreviaturas": ["ZAC", "AGS", "GTO", "QRO"],
        "carreteras_clave": ["MEX-45", "MEX-57", "MEX-90"],
        "cuentas_x": [
            "TraficoQuerétaro", "VialGuanajuato", "InfovialBajio",
            "TraficoLeon", "PCGuanajuato",
        ],
        "keywords": ["queretaro", "guanajuato", "zacatecas", "aguascalientes",
                     "leon", "irapuato", "accidente", "bloqueo", "protesta"],
        "casetas_capufe": ["Querétaro", "León", "Zacatecas", "Aguascalientes"],
    },
    "centro": {
        "nombre": "Centro / Valle de México",
        "emoji": "🏙️",
        "estados": ["Ciudad de México", "Estado de México", "Hidalgo",
                    "Tlaxcala", "Puebla", "Morelos"],
        "abreviaturas": ["CDMX", "EDOMEX", "HGO", "TLAX", "PUE", "MOR"],
        "carreteras_clave": ["MEX-57D", "MEX-150D", "MEX-85D", "MEX-95D", "MEX-190"],
        "cuentas_x": [
            "OVIALCDMX", "C5_CDMX", "TraficoMexicoCity",
            "VialEdomex", "InfovialPuebla", "PCPuebla",
        ],
        "keywords": ["cdmx", "ciudad de mexico", "estado de mexico", "puebla",
                     "hidalgo", "morelos", "accidente", "manifestacion", "corte",
                     "cierre", "volcán", "popocatepetl"],
        "casetas_capufe": ["CDMX", "Puebla", "Cuernavaca", "Pachuca"],
    },
    "golfo": {
        "nombre": "Golfo / Sureste",
        "emoji": "🌴",
        "estados": ["Veracruz", "Tabasco", "Oaxaca", "Chiapas"],
        "abreviaturas": ["VER", "TAB", "OAX", "CHIS"],
        "carreteras_clave": ["MEX-150D", "MEX-180D", "MEX-190"],
        "cuentas_x": [
            "TraficoVeracruz", "VialOaxaca", "InfovialGolfo",
            "PCVeracruz", "TraficoChiapas",
        ],
        "keywords": ["veracruz", "tabasco", "oaxaca", "chiapas", "villahermosa",
                     "tuxtla", "accidente", "manifestacion", "bloqueo", "lluvia"],
        "casetas_capufe": ["Veracruz", "Villahermosa", "Tuxtla Gutiérrez", "Oaxaca"],
    },
    "peninsula": {
        "nombre": "Península de Yucatán",
        "emoji": "🦜",
        "estados": ["Campeche", "Yucatán", "Quintana Roo"],
        "abreviaturas": ["CAMP", "YUC", "QROO"],
        "carreteras_clave": ["MEX-180", "MEX-261", "MEX-307"],
        "cuentas_x": [
            "TraficoMerida", "VialYucatan", "InfovialPeninsula",
            "PCYucatan", "TraficoCanicun",
        ],
        "keywords": ["yucatan", "campeche", "quintana roo", "merida", "cancun",
                     "accidente", "huracan", "lluvia", "inundacion"],
        "casetas_capufe": ["Mérida", "Cancún", "Campeche"],
    },
}

# Mapa estado → región
ESTADO_A_REGION = {}
for region_key, data in REGIONS.items():
    for estado in data["estados"]:
        ESTADO_A_REGION[estado.lower()] = region_key
    for abr in data["abreviaturas"]:
        ESTADO_A_REGION[abr.lower()] = region_key


def get_region_por_estado(estado: str) -> str | None:
    return ESTADO_A_REGION.get(estado.lower())


def get_regions_info(region_keys: list[str]) -> list[dict]:
    return [
        {"key": k, **REGIONS[k]}
        for k in region_keys
        if k in REGIONS
    ]
