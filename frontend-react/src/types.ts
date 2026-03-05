// ── Summary (/dashboard/summary) ─────────────────────────────────────────────
export interface Summary {
  total_readings:  number | null
  avg_power:       number | null
  max_power:       number | null
  total_faults:    number | null   // ← era fault_count
  max_fault_proba: number | null
  last_ts:         string | null   // ← era last_timestamp
}

// ── Timeseries (/dashboard/timeseries) ───────────────────────────────────────
export interface TimeseriesItem {
  ts:                    string
  plant_id?:             number | null
  power_ac_kw?:          number | null
  expected_power_ac_kw?: number | null
  power_residual_kw?:    number | null  // ← era residual_kw
  fault_proba?:          number | null
}

// ── Alerts (/dashboard/alerts) ───────────────────────────────────────────────
export interface AlertItem {
  ts?:                   string | null
  plant_id?:             number | null
  model_version?:        string
  expected_power_ac_kw?: number | null
  power_residual_kw?:    number | null
  fault_proba?:          number | null
  fault_pred?:           number | null
  created_at?:           string | null
}

// ── Params ───────────────────────────────────────────────────────────────────
export interface DashboardParams {
  plant_id: number
  hours:    number
  min_proba: number
}