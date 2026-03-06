// ── Summary (/dashboard/summary) ─────────────────────────────────────────────
export interface Summary {
  total_readings:  number | null
  avg_power:       number | null
  max_power:       number | null
  total_faults:    number | null
  max_fault_proba: number | null
  last_ts:         string | null
}

// ── Timeseries (/dashboard/timeseries) ───────────────────────────────────────
export interface TimeseriesItem {
  ts:                    string
  plant_id?:             number | null
  power_ac_kw?:          number | null
  expected_power_ac_kw?: number | null
  power_residual_kw?:    number | null
  fault_proba?:          number | null
}

// ── Alerts (/dashboard/alerts) ───────────────────────────────────────────────
export interface AlertItem {
  id?:                   number | null   // prediction_id para XAI
  ts?:                   string | null
  plant_id?:             number | null
  model_version?:        string
  expected_power_ac_kw?: number | null
  power_residual_kw?:    number | null
  fault_proba?:          number | null
  fault_pred?:           number | null
  created_at?:           string | null
}

// ── XAI (/explain/{prediction_id}) ───────────────────────────────────────────
export interface ExplainResult {
  prediction_id:        number
  cached:               boolean
  fault_proba:          number | null
  expected_value:       number | null
  top_reasons:          Record<string, number>
  explanation_text:     string
  // Nuevos campos
  inferred_fault_type:  string | null
  fault_type_label:     string | null
  analysis_text:        string | null
  recommendation_text:  string | null
  reading_count:        number | null
  duration_minutes:     number | null
}

// ── Params ───────────────────────────────────────────────────────────────────
export interface DashboardParams {
  plant_id:  number
  hours:     number
  min_proba: number
}
// ── Fault Packages (/dashboard/fault-packages) ───────────────────────────────
export interface FaultPackage {
  start_ts:                    string
  end_ts:                      string
  plant_id:                    number
  reading_count:               number
  duration_minutes:            number
  max_fault_proba:             number
  representative_id:           number        // prediction_id con mayor proba → va al XAI
  representative_expected_kw:  number | null
  representative_residual_kw:  number | null
  model_version:               string | null
}