"""
Importador mensual de datos SESNSP — Robos a transportista de carga en carretera.
Fuente oficial: Secretariado Ejecutivo del SNSP (datos abiertos gratuitos).
https://www.gob.mx/sesnsp/acciones-y-programas/datos-abiertos-de-incidencia-delictiva

Ejecutar 1 vez al mes (1° de cada mes via GitHub Actions).
Descarga el Excel más reciente, filtra "Robo a transportista" y guarda en Supabase.
"""
import os
import sys
import re
import logging
import io
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Página de datos abiertos SESNSP
SESNSP_PAGE = (
    "https://www.gob.mx/sesnsp/acciones-y-programas/"
    "datos-abiertos-de-incidencia-delictiva"
)
# Patrón del nombre del archivo Excel municipal
_FILE_PATTERN = re.compile(r"IDSC_Municipal[^\"'\s]+\.xlsx", re.IGNORECASE)

# Coordenadas centroide por estado para geocodificación
ESTADO_COORDS: dict[str, tuple[float, float]] = {
    "Aguascalientes":    (21.88, -102.30),
    "Baja California":   (30.84, -115.28),
    "Baja California Sur": (25.19, -111.63),
    "Campeche":          (18.93,  -90.53),
    "Chiapas":           (16.75,  -93.11),
    "Chihuahua":         (28.63, -106.07),
    "Ciudad de México":  (19.43,  -99.13),
    "Coahuila de Zaragoza": (27.06, -101.71),
    "Colima":            (19.24, -103.72),
    "Durango":           (24.02, -104.66),
    "Guanajuato":        (21.02, -101.26),
    "Guerrero":          (17.43, -100.00),
    "Hidalgo":           (20.12,  -98.73),
    "Jalisco":           (20.68, -103.35),
    "México":            (19.29,  -99.66),
    "Michoacán de Ocampo": (19.70, -101.19),
    "Morelos":           (18.68,  -99.10),
    "Nayarit":           (21.50, -104.90),
    "Nuevo León":        (25.68, -100.32),
    "Oaxaca":            (17.06,  -96.72),
    "Puebla":            (19.04,  -98.20),
    "Querétaro":         (20.60, -100.39),
    "Quintana Roo":      (21.16,  -86.85),
    "San Luis Potosí":   (22.15, -100.98),
    "Sinaloa":           (24.80, -107.40),
    "Sonora":            (29.07, -110.97),
    "Tabasco":           (17.99,  -92.93),
    "Tamaulipas":        (23.74,  -99.15),
    "Tlaxcala":          (19.31,  -98.24),
    "Veracruz de Ignacio de la Llave": (19.20, -96.13),
    "Yucatán":           (20.97,  -89.62),
    "Zacatecas":         (22.77, -102.58),
}

# Términos de búsqueda en las columnas del Excel
_SUBTIPO_ROBOS = ["transportista", "carga en carretera", "robo a transporte"]


def _buscar_archivo_sesnsp() -> str | None:
    """Extrae la URL del Excel más reciente de la página SESNSP."""
    try:
        r = requests.get(SESNSP_PAGE, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        matches = _FILE_PATTERN.findall(r.text)
        if not matches:
            # Buscar enlace que contenga 'IDSC' o 'incidencia'
            urls = re.findall(r'https?://[^\s"\']+(?:IDSC|idsc)[^\s"\']*\.xlsx', r.text)
            if urls:
                return urls[0]
            return None
        # La página referencia solo el nombre — construir URL cms
        filename = matches[0]
        cms_urls = re.findall(
            rf'https://www\.gob\.mx/cms/uploads/attachment/file/\d+/{re.escape(filename)}',
            r.text,
        )
        return cms_urls[0] if cms_urls else None
    except Exception as e:
        logger.error(f"Error buscando archivo SESNSP: {e}")
        return None


def _descargar_excel(url: str) -> bytes | None:
    try:
        logger.info(f"Descargando: {url}")
        r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return r.content
    except Exception as e:
        logger.error(f"Error descargando Excel: {e}")
        return None


def _procesar_excel(contenido: bytes) -> list[dict]:
    """
    Parsea el Excel SESNSP y extrae filas de robo a transportista de carga.
    Retorna lista de dicts listos para insertar en Supabase.
    """
    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas no instalado — pip install pandas openpyxl")
        return []

    try:
        df = pd.read_excel(io.BytesIO(contenido), header=None, dtype=str)
    except Exception as e:
        logger.error(f"Error leyendo Excel: {e}")
        return []

    logger.info(f"Excel cargado: {df.shape[0]} filas × {df.shape[1]} columnas")

    # Encontrar fila de encabezado (contiene "Entidad" y "Municipio")
    header_row = None
    for i, row in df.iterrows():
        vals = [str(v).lower() for v in row.values]
        if "entidad" in vals and "municipio" in vals:
            header_row = i
            break

    if header_row is None:
        logger.error("No se encontró fila de encabezado en el Excel")
        return []

    df.columns = df.iloc[header_row]
    df = df.iloc[header_row + 1:].reset_index(drop=True)

    # Normalizar nombres de columnas
    df.columns = [str(c).strip() for c in df.columns]

    # Buscar columnas clave
    col_entidad   = next((c for c in df.columns if "entidad"   in c.lower()), None)
    col_municipio = next((c for c in df.columns if "municipio" in c.lower()), None)
    col_subtipo   = next((c for c in df.columns if "subtipo"   in c.lower()), None)
    col_modalidad = next((c for c in df.columns if "modalidad" in c.lower()), None)

    if not col_entidad:
        logger.error("Columna 'Entidad' no encontrada")
        return []

    # Detectar columnas de meses (formato: Enero, Febrero... o 1, 2...)
    meses_es = ["enero","febrero","marzo","abril","mayo","junio",
                "julio","agosto","septiembre","octubre","noviembre","diciembre"]
    mes_cols: list[tuple[int, str]] = []  # (num_mes, nombre_col)
    for col in df.columns:
        col_lower = col.lower()
        for i, mes in enumerate(meses_es, 1):
            if mes in col_lower:
                mes_cols.append((i, col))
                break

    if not mes_cols:
        logger.warning("No se detectaron columnas de meses")

    # Filtrar filas de robo a transportista
    mask = pd.Series([False] * len(df))
    for col in [col_subtipo, col_modalidad]:
        if col and col in df.columns:
            for termino in _SUBTIPO_ROBOS:
                mask |= df[col].fillna("").str.lower().str.contains(termino, na=False)

    df_robos = df[mask].copy()
    logger.info(f"Filas de robo a transportista encontradas: {len(df_robos)}")

    if df_robos.empty:
        logger.warning("Sin datos de robo a transportista en este archivo")
        return []

    # Detectar año del archivo (buscar en nombre o en datos)
    from datetime import datetime
    año_actual = datetime.now().year

    registros = []
    for _, row in df_robos.iterrows():
        entidad   = str(row.get(col_entidad, "") or "").strip()
        municipio = str(row.get(col_municipio, "") or "").strip() if col_municipio else ""

        if not entidad or entidad.lower() in ("nan", "none", ""):
            continue

        coords = ESTADO_COORDS.get(entidad)
        lat = coords[0] if coords else None
        lon = coords[1] if coords else None

        # Crear registro por cada mes
        for num_mes, col_mes in mes_cols:
            val = row.get(col_mes, 0)
            try:
                total = int(float(str(val))) if str(val) not in ("nan","None","") else 0
            except (ValueError, TypeError):
                total = 0

            if total == 0:
                continue

            registros.append({
                "año":       año_actual,
                "mes":       num_mes,
                "entidad":   entidad,
                "municipio": municipio,
                "total":     total,
                "coords_lat": lat,
                "coords_lon": lon,
            })

    logger.info(f"Registros a guardar: {len(registros)}")
    return registros


def _guardar(registros: list[dict]):
    from db.supabase_client import guardar_robos_sesnsp
    if registros:
        guardar_robos_sesnsp(registros)
        logger.info(f"✅ {len(registros)} registros guardados en robos_sesnsp")
    else:
        logger.warning("Sin registros que guardar")


def main():
    logger.info("=== Importador SESNSP — inicio ===")

    url = _buscar_archivo_sesnsp()
    if not url:
        logger.error("No se encontró URL del archivo SESNSP. Verifica manualmente en:")
        logger.error(SESNSP_PAGE)
        sys.exit(1)

    contenido = _descargar_excel(url)
    if not contenido:
        sys.exit(1)

    registros = _procesar_excel(contenido)
    _guardar(registros)

    logger.info("=== Importador SESNSP — completado ===")


if __name__ == "__main__":
    main()
