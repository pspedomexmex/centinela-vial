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
  fecha          DATE GENERATED ALWAYS AS (DATE(registrado_en)) STORED,
  dia_semana     SMALLINT GENERATED ALWAYS AS (EXTRACT(DOW FROM registrado_en)::SMALLINT) STORED,
  hora_del_dia   SMALLINT GENERATED ALWAYS AS (EXTRACT(HOUR FROM registrado_en)::SMALLINT) STORED,
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
