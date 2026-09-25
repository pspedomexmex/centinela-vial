-- Ejecutar en Supabase → SQL Editor

CREATE TABLE IF NOT EXISTS viajes (
  id          SERIAL PRIMARY KEY,
  chat_id     BIGINT UNIQUE NOT NULL,
  origen      TEXT NOT NULL,
  destino     TEXT NOT NULL,
  origen_fmt  TEXT DEFAULT '',
  destino_fmt TEXT DEFAULT '',
  regiones    JSONB NOT NULL DEFAULT '[]',
  estados     JSONB NOT NULL DEFAULT '[]',
  distancia_km INTEGER,
  duracion_hrs REAL,
  city_path   JSONB DEFAULT NULL,
  creado_en   TIMESTAMPTZ DEFAULT NOW(),
  activo      BOOLEAN DEFAULT TRUE
);

-- Migración para tablas existentes:
-- ALTER TABLE viajes ADD COLUMN IF NOT EXISTS city_path JSONB DEFAULT NULL;

CREATE TABLE IF NOT EXISTS alertas_enviadas (
  id          SERIAL PRIMARY KEY,
  chat_id     BIGINT NOT NULL,
  hash_alerta TEXT NOT NULL,
  enviado_en  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(chat_id, hash_alerta)
);

CREATE TABLE IF NOT EXISTS cierres_activos (
  id           SERIAL PRIMARY KEY,
  chat_id      BIGINT NOT NULL,
  hash_cierre  TEXT NOT NULL,
  descripcion  TEXT NOT NULL,
  detectado_en TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(chat_id, hash_cierre)
);

-- Migración para bases existentes:
-- CREATE TABLE IF NOT EXISTS cierres_activos (
--   id SERIAL PRIMARY KEY, chat_id BIGINT NOT NULL, hash_cierre TEXT NOT NULL,
--   descripcion TEXT NOT NULL, detectado_en TIMESTAMPTZ DEFAULT NOW(),
--   UNIQUE(chat_id, hash_cierre)
-- );

CREATE INDEX IF NOT EXISTS idx_viajes_activos ON viajes(activo) WHERE activo = TRUE;
CREATE INDEX IF NOT EXISTS idx_alertas ON alertas_enviadas(chat_id, hash_alerta);
CREATE INDEX IF NOT EXISTS idx_cierres ON cierres_activos(chat_id);

-- ─────────────────────────────────────────────────────────────────
-- HISTÓRICO DE INCIDENTES — dataset para tesis de maestría
-- Acumula cada incidente detectado con contexto temporal y geográfico.
-- UNIQUE (hash_contenido, fecha) → un registro por incidente por día.
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS incidentes_historico (
  id             BIGSERIAL PRIMARY KEY,
  registrado_en  TIMESTAMPTZ DEFAULT NOW(),
  fecha          DATE,
  dia_semana     SMALLINT,
  hora_del_dia   SMALLINT,
  origen         TEXT,
  destino        TEXT,
  city_path      JSONB,
  tipo           TEXT,
  descripcion    TEXT,
  severidad      SMALLINT DEFAULT 0,
  fuente         TEXT DEFAULT 'TomTom',
  hora_incidente TEXT,
  coords_lat     FLOAT,
  coords_lon     FLOAT,
  hash_contenido TEXT NOT NULL,
  UNIQUE(hash_contenido, fecha)
);

CREATE INDEX IF NOT EXISTS idx_hist_fecha      ON incidentes_historico(fecha);
CREATE INDEX IF NOT EXISTS idx_hist_tipo       ON incidentes_historico(tipo);
CREATE INDEX IF NOT EXISTS idx_hist_ruta       ON incidentes_historico(origen, destino);
CREATE INDEX IF NOT EXISTS idx_hist_dia_hora   ON incidentes_historico(dia_semana, hora_del_dia);
CREATE INDEX IF NOT EXISTS idx_hist_coords     ON incidentes_historico(coords_lat, coords_lon)
  WHERE coords_lat IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────
-- CLIMA HISTÓRICO — snapshot de las 55 ciudades por hora de muestreo
-- Cubre temperatura, precipitación, viento, visibilidad y código WMO.
-- UNIQUE (ciudad, fecha, hora_del_dia) → un registro por ciudad por hora.
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clima_historico (
  id             BIGSERIAL PRIMARY KEY,
  registrado_en  TIMESTAMPTZ DEFAULT NOW(),
  fecha          DATE,
  dia_semana     SMALLINT,
  hora_del_dia   SMALLINT,
  ciudad         TEXT NOT NULL,
  lat            FLOAT,
  lon            FLOAT,
  codigo_wmo     SMALLINT,
  descripcion    TEXT,
  temperatura    FLOAT,
  precipitacion  FLOAT,
  viento_kmh     FLOAT,
  visibilidad_m  FLOAT,
  es_severo      BOOLEAN DEFAULT FALSE,
  UNIQUE(ciudad, fecha, hora_del_dia)
);

CREATE INDEX IF NOT EXISTS idx_clima_fecha     ON clima_historico(fecha);
CREATE INDEX IF NOT EXISTS idx_clima_ciudad    ON clima_historico(ciudad);
CREATE INDEX IF NOT EXISTS idx_clima_severo    ON clima_historico(fecha) WHERE es_severo = TRUE;
CREATE INDEX IF NOT EXISTS idx_clima_dia_hora  ON clima_historico(dia_semana, hora_del_dia);

-- ─────────────────────────────────────────────────────────────────
-- FLUJO HISTÓRICO — velocidad actual vs libre en las 55 ciudades
-- Permite analizar patrones de congestión por hora, día y ciudad.
-- UNIQUE (ciudad, fecha, hora_del_dia) → un snapshot por ciudad por hora.
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS flujo_historico (
  id               BIGSERIAL PRIMARY KEY,
  registrado_en    TIMESTAMPTZ DEFAULT NOW(),
  fecha            DATE,
  dia_semana       SMALLINT,
  hora_del_dia     SMALLINT,
  ciudad           TEXT NOT NULL,
  velocidad_actual FLOAT,
  velocidad_libre  FLOAT,
  ratio_flujo      FLOAT,
  nivel            TEXT,   -- NORMAL | LENTO | MUY_LENTO
  UNIQUE(ciudad, fecha, hora_del_dia)
);

CREATE INDEX IF NOT EXISTS idx_flujo_fecha     ON flujo_historico(fecha);
CREATE INDEX IF NOT EXISTS idx_flujo_ciudad    ON flujo_historico(ciudad);
CREATE INDEX IF NOT EXISTS idx_flujo_nivel     ON flujo_historico(nivel, fecha);
CREATE INDEX IF NOT EXISTS idx_flujo_dia_hora  ON flujo_historico(dia_semana, hora_del_dia);
