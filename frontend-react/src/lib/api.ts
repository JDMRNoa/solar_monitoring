import type { Summary, TimeseriesItem, AlertItem } from '../types'

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
  return res.json() as Promise<T>
}

export function fetchSummary(plant_id: number, hours: number): Promise<Summary> {
  return get<Summary>(`/dashboard/summary?plant_id=${plant_id}&hours=${hours}`)
}

// El backend devuelve { data: [...] }
export async function fetchTimeseries(plant_id: number, hours: number): Promise<TimeseriesItem[]> {
  const res = await get<{ data?: TimeseriesItem[] } | TimeseriesItem[]>(
    `/dashboard/timeseries?plant_id=${plant_id}&hours=${hours}`
  )
  if (Array.isArray(res)) return res
  return (res as { data?: TimeseriesItem[] }).data ?? []
}

// El backend devuelve { data: [...] } o array directo
export async function fetchAlerts(plant_id: number, hours: number, min_proba: number): Promise<AlertItem[]> {
  const res = await get<{ data?: AlertItem[] } | AlertItem[]>(
    `/dashboard/alerts?plant_id=${plant_id}&hours=${hours}&min_proba=${min_proba}`
  )
  if (Array.isArray(res)) return res
  return (res as { data?: AlertItem[] }).data ?? []
}