// src/hooks/useLiveWeather.ts
import { useEffect, useState } from 'react'

export interface LivePlantData {
  plant_id: number
  inverter_id?: string
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
  fault_type_pred?: string
  inverters?: LivePlantData[]
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
        const payload = JSON.parse(e.data) as { inverters: LivePlantData[] }
        setData(prev => {
          const next = { ...prev }
          const groups: Record<number, LivePlantData[]> = {}
          
          for (const inv of payload.inverters) {
            if (!groups[inv.plant_id]) groups[inv.plant_id] = []
            groups[inv.plant_id].push(inv)
          }

          for (const [pidStr, invs] of Object.entries(groups)) {
            const pid = Number(pidStr)
            invs.sort((a, b) => (a.inverter_id || '').localeCompare(b.inverter_id || ''))
            
            const first = invs[0]
            const highestProbaInv = invs.reduce((a, b) => (a.fault_proba || 0) > (b.fault_proba || 0) ? a : b)
            
            const aggregated: LivePlantData = {
              ...first,
              power_ac_kw: invs.reduce((sum, inv) => sum + (inv.power_ac_kw || 0), 0),
              energy_daily_kwh: invs.reduce((sum, inv) => sum + (inv.energy_daily_kwh || 0), 0),
              fault_proba: highestProbaInv.fault_proba,
              fault_pred: highestProbaInv.fault_pred,
              fault_type_pred: highestProbaInv.fault_type_pred,
              power_residual_kw: invs.reduce((sum, inv) => sum + (inv.power_residual_kw || 0), 0),
              inverters: invs
            }
            
            next[pid] = aggregated
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