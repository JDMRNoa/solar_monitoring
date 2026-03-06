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
  prediction_id:    number
  cached:           boolean
  fault_proba:      number | null
  expected_value:   number | null
  top_reasons:      Record<string, number>
  explanation_text: string
}

// ── Params ───────────────────────────────────────────────────────────────────
export interface DashboardParams {
  plant_id:  number
  hours:     number
  min_proba: number
}