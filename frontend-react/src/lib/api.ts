import type { Summary, TimeseriesItem, AlertItem, ExplainResult } from '../types'

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
  return res.json() as Promise<T>
}

export function fetchSummary(plant_id: number, hours: number): Promise<Summary> {
  return get<Summary>(`/dashboard/summary?plant_id=${plant_id}&hours=${hours}`)
}

export async function fetchTimeseries(plant_id: number, hours: number): Promise<TimeseriesItem[]> {
  const res = await get<{ data?: TimeseriesItem[] } | TimeseriesItem[]>(
    `/dashboard/timeseries?plant_id=${plant_id}&hours=${hours}`
  )
  if (Array.isArray(res)) return res
  return (res as { data?: TimeseriesItem[] }).data ?? []
}

export async function fetchAlerts(plant_id: number, hours: number, min_proba: number): Promise<AlertItem[]> {
  const res = await get<{ data?: AlertItem[] } | AlertItem[]>(
    `/dashboard/alerts?plant_id=${plant_id}&hours=${hours}&min_proba=${min_proba}`
  )
  if (Array.isArray(res)) return res
  return (res as { data?: AlertItem[] }).data ?? []
}

export function fetchExplain(
  prediction_id: number,
  reading_count = 1,
  duration_minutes = 0,
): Promise<ExplainResult> {
  return get<ExplainResult>(
    `/explain/${prediction_id}?reading_count=${reading_count}&duration_minutes=${duration_minutes}`
  )
}
export async function fetchFaultPackages(
  plant_id: number,
  hours: number,
  min_proba = 0.3,
  gap_minutes = 30
): Promise<import('../types').FaultPackage[]> {
  const res = await get<{ data?: import('../types').FaultPackage[] } | import('../types').FaultPackage[]>(
    `/dashboard/fault-packages?plant_id=${plant_id}&hours=${hours}&min_proba=${min_proba}&gap_minutes=${gap_minutes}`
  )
  if (Array.isArray(res)) return res
  return (res as { data?: import('../types').FaultPackage[] }).data ?? []
}