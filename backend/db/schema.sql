CREATE TABLE IF NOT EXISTS solar_readings (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL,
  plant_id INT NOT NULL,
  irradiance_wm2 DOUBLE PRECISION,
  temp_ambient_c DOUBLE PRECISION,
  temp_module_c DOUBLE PRECISION,
  power_ac_kw DOUBLE PRECISION,
  power_dc_kw DOUBLE PRECISION,
  energy_daily_kwh DOUBLE PRECISION,
  energy_total_kwh DOUBLE PRECISION,
  label_is_fault INT DEFAULT 0,
  fault_type TEXT,
  fault_severity INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_solar_readings_ts ON solar_readings(ts);
CREATE INDEX IF NOT EXISTS idx_solar_readings_plant_ts ON solar_readings(plant_id, ts);

CREATE TABLE IF NOT EXISTS ai_predictions (
  id BIGSERIAL PRIMARY KEY,
  reading_id BIGINT NOT NULL REFERENCES solar_readings(id) ON DELETE CASCADE,
  model_version TEXT DEFAULT 'v1',
  expected_power_ac_kw DOUBLE PRECISION,
  power_residual_kw DOUBLE PRECISION,
  fault_proba DOUBLE PRECISION,
  fault_pred INT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_predictions_reading ON ai_predictions(reading_id);

CREATE TABLE IF NOT EXISTS ai_explanations (
  id BIGSERIAL PRIMARY KEY,
  prediction_id BIGINT NOT NULL REFERENCES ai_predictions(id) ON DELETE CASCADE,
  explanation_text TEXT,
  top_reasons JSONB,
  shap_waterfall_path TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_explanations_pred ON ai_explanations(prediction_id);
