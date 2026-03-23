import type { Summary, TimeseriesItem, AlertItem, ExplainResult } from '../types'

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

import Cookies from 'js-cookie'

async function get<T>(path: string): Promise<T> {
  const token = Cookies.get('solarmonitor_jwt')
  const headers: HeadersInit = {}
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${BASE}${path}`, { headers })
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

export function fetchExplain(prediction_id: number): Promise<ExplainResult> {
  return get<ExplainResult>(`/explain/${prediction_id}`)
}

export async function fetchFaultPackages(
  plant_id: number,
  hours: number | null,
  min_proba = 0.3,
  gap_minutes = 30,
): Promise<import('../types').FaultPackage[]> {
  const hoursParam = hours != null ? `&hours=${hours}` : ''
  const res = await get<import('../types').FaultPackage[]>(
    `/dashboard/fault-packages?plant_id=${plant_id}${hoursParam}&min_proba=${min_proba}&gap_minutes=${gap_minutes}`
  )
  return Array.isArray(res) ? res : []
}

export async function fetchFaultEvents(
  plant_id: number,
  hours: number | null,
  min_proba = 0.5,
  limit = 200,
): Promise<import('../types').FaultEvent[]> {
  const hoursParam = hours != null ? `&hours=${hours}` : ''
  const res = await get<import('../types').FaultEvent[]>(
    `/dashboard/events?plant_id=${plant_id}${hoursParam}&min_proba=${min_proba}&limit=${limit}`
  )
  return Array.isArray(res) ? res : []
}

export async function sendChatMessage(
  plant_id: number,
  period_hours: number,
  messages: { role: string; content: string }[],
  onChunk: (text: string) => void
): Promise<void> {
  const token = Cookies.get('solarmonitor_jwt')
  const headers: HeadersInit = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${BASE}/chat/`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ plant_id, period_hours, messages })
  })

  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
  
  const reader = res.body?.getReader()
  if (!reader) return
  
  const decoder = new TextDecoder("utf-8")
  let buffer = ""
  
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ""
    
    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const obj = JSON.parse(line)
        if (obj.message?.content) {
          onChunk(obj.message.content)
        }
      } catch (e) {
        console.error("Error parsing chat chunk:", e)
      }
    }
  }
}