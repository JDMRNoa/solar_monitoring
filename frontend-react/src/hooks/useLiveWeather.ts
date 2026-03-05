// src/hooks/useLiveWeather.ts
import { useEffect, useState } from 'react'

export interface LivePlantData {
  plant_id: number
  ts: string | null
  // Clima
  cloud_cover: number | null
  wind_ms: number | null
  rain_active: boolean
  soiling: number | null
  degradation_pct: number | null
  elevation_deg: number | null
  // Lectura
  irradiance_wm2: number | null
  temp_ambient_c: number | null
  temp_module_c: number | null
  power_ac_kw: number | null
  energy_daily_kwh: number | null
  label_is_fault: number
  fault_type: string
  fault_severity: number
  // ML
  fault_proba: number | null
  fault_pred: number | null
  expected_power_ac_kw: number | null
  power_residual_kw: number | null
}

const BASE = (import.meta as any).env?.VITE_API_BASE_URL ?? '/api'

export function useLiveWeather() {
  const [data, setData] = useState<Record<number, LivePlantData>>({})
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    const es = new EventSource(`${BASE}/live/weather`)

    es.onopen = () => setConnected(true)

    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data) as { plants: LivePlantData[] }
        setData(prev => {
          const next = { ...prev }
          for (const p of payload.plants) {
            next[p.plant_id] = p
          }
          return next
        })
      } catch {
        // ignorar mensajes malformados
      }
    }

    es.onerror = () => {
      setConnected(false)
      // EventSource reconecta automáticamente
    }

    return () => {
      es.close()
      setConnected(false)
    }
  }, [])

  return { data, connected }
}