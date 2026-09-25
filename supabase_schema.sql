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

CREATE INDEX IF NOT EXISTS idx_viajes_activos ON viajes(activo) WHERE activo = TRUE;
CREATE INDEX IF NOT EXISTS idx_alertas ON alertas_enviadas(chat_id, hash_alerta);
