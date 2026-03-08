import { useState, useCallback, useEffect } from 'react'
import type { Summary, TimeseriesItem, FaultPackage, PlantThresholds } from '../types'
import { fetchSummary, fetchTimeseries, fetchFaultPackages } from '../lib/api'
import { PowerChart, ResidualFaultChart, TempIrradianceChart, PerformanceRatioChart } from '../components/Charts'
import AlertsTable from '../components/AlertsTable'

// ── Helpers ───────────────────────────────────────────────────────────────────

function safeFixed(v: number | null | undefined, d = 2) {
  if (v == null || isNaN(v)) return '—'
  return v.toFixed(d)
}
function safePct(v: number | null | undefined) {
  if (v == null || isNaN(v)) return '—'
  return `${(v * 100).toFixed(1)}%`
}
function safeInt(v: number | null | undefined) {
  if (v == null || isNaN(v)) return '—'
  return `${v}`
}

// ── Planta metadata ───────────────────────────────────────────────────────────

const PLANTS = [
  { label: 'P1 – Caribe (Barranquilla)',  value: 1, capacity_kw: 200 },
  { label: 'P2 – Andina (Bogotá)',        value: 2, capacity_kw: 80  },
  { label: 'P3 – Paisa (Medellín)',       value: 3, capacity_kw: 150 },
  { label: 'P4 – Valle (Cali)',           value: 4, capacity_kw: 120 },
  { label: 'P5 – Llanos (Villavicencio)', value: 5, capacity_kw: 90  },
  { label: 'P6 – Guajira (Riohacha)',     value: 6, capacity_kw: 300 },
  { label: 'P7 – Sierra Nevada',         value: 7, capacity_kw: 60  },
  { label: 'P8 – Boyacá (Tunja)',         value: 8, capacity_kw: 45  },
]

const DEFAULT_THRESHOLD = 0.3

// ── KPI Card ──────────────────────────────────────────────────────────────────

function KpiCard({ label, value, sub, accent }: {
  label: string; value: string; sub?: string; accent?: string
}) {
  return (
    <div style={{ background: 'var(--surface-2)', border: `1px solid ${accent ? accent + '44' : 'var(--border)'}`, borderRadius: '6px', padding: '14px 16px' }}>
      <p style={{ fontSize: '0.6rem', color: 'var(--text-dim)', letterSpacing: '0.1em', margin: '0 0 6px' }}>{label}</p>
      <p style={{ fontSize: '1.35rem', fontFamily: 'Syne, sans-serif', fontWeight: 700, color: accent ?? '#fff', lineHeight: 1, margin: 0 }}>{value}</p>
      {sub && <p style={{ fontSize: '0.6rem', color: 'var(--text-dim)', marginTop: '4px', margin: '4px 0 0' }}>{sub}</p>}
    </div>
  )
}

// ── Select ────────────────────────────────────────────────────────────────────

function Select({ label, value, options, onChange }: {
  label: string; value: string | number
  options: { label: string; value: string | number }[]
  onChange: (v: string) => void
}) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.6rem', color: 'var(--text-dim)', letterSpacing: '0.08em' }}>
      {label}
      <select
        value={value} onChange={e => onChange(e.target.value)}
        style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '4px', color: '#c9d1d9', padding: '5px 8px', fontSize: '0.75rem', fontFamily: 'JetBrains Mono, monospace', outline: 'none', cursor: 'pointer' }}
      >
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  )
}

// ── Threshold slider ──────────────────────────────────────────────────────────

function ThresholdSlider({ plantId, thresholds, onChange }: {
  plantId: number; thresholds: PlantThresholds; onChange: (pid: number, v: number) => void
}) {
  const value = thresholds[plantId] ?? DEFAULT_THRESHOLD
  const pct   = Math.round(value * 100)
  const color = value >= 0.8 ? '#3fb950' : value >= 0.5 ? '#f59e0b' : '#f85149'

  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.6rem', color: 'var(--text-dim)', letterSpacing: '0.08em', minWidth: '140px' }}>
      <span style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>UMBRAL FALLA</span>
        <span style={{ color, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700 }}>≥ {pct}%</span>
      </span>
      <input type="range" min={10} max={95} step={5} value={pct}
        onChange={e => onChange(plantId, Number(e.target.value) / 100)}
        style={{ accentColor: color, cursor: 'pointer', width: '100%', height: '4px' }}
      />
      <span style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.55rem' }}>
        <span>10%</span>
        <span style={{ color: 'var(--text-dim)' }}>{value !== DEFAULT_THRESHOLD ? '· ajustado' : '· global'}</span>
        <span>95%</span>
      </span>
    </label>
  )
}

// ── Loading / Error ───────────────────────────────────────────────────────────

function Spinner() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '64px 0', color: 'var(--text-dim)', fontSize: '0.7rem', gap: '8px' }}>
      <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
        <path d="M12 2a10 10 0 0 1 10 10" />
      </svg>
      CARGANDO...
    </div>
  )
}

function ErrorMsg({ msg }: { msg: string }) {
  return (
    <div style={{ border: '1px solid #f8514944', borderRadius: '6px', color: '#f85149', fontSize: '0.7rem', background: '#f8514910', padding: '16px' }}>
      ERROR: {msg}
    </div>
  )
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

type LoadState = 'idle' | 'loading' | 'success' | 'error'

interface DashboardProps {
  onLastTimestamp?: (ts: string | null) => void
  initialPlantId?: number
  onPlantChange?: (plantId: number) => void
}

export default function Dashboard({ onLastTimestamp, initialPlantId = 1, onPlantChange }: DashboardProps) {
  const [plantId, setPlantId]         = useState(initialPlantId)
  const [hours, setHours]             = useState(11000)
  const [thresholds, setThresholds]   = useState<PlantThresholds>({})
  const [state, setState]             = useState<LoadState>('idle')
  const [error, setError]             = useState<string | null>(null)
  const [summary, setSummary]         = useState<Summary | null>(null)
  const [tsData, setTsData]           = useState<TimeseriesItem[]>([])
  const [packages, setPackages]       = useState<FaultPackage[]>([])
  const [pendingLoad, setPendingLoad] = useState(false)

  const plantMeta  = PLANTS.find(p => p.value === plantId) ?? PLANTS[0]
  const capacityKw = plantMeta.capacity_kw

  const load = useCallback(async () => {
    setPendingLoad(false)
    setState('loading')
    setError(null)
    const threshold = thresholds[plantId] ?? DEFAULT_THRESHOLD
    try {
      const [s, ts, pkgs] = await Promise.all([
        fetchSummary(plantId, hours),
        fetchTimeseries(plantId, hours),
        fetchFaultPackages(plantId, hours, threshold),
      ])
      setSummary(s)
      setTsData(Array.isArray(ts) ? ts : [])
      setPackages(Array.isArray(pkgs) ? pkgs : [])
      const lastTs = s.last_ts ?? (Array.isArray(ts) && ts.length > 0 ? ts[ts.length - 1].ts : null)
      onLastTimestamp?.(lastTs)
      setState('success')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setState('error')
    }
  }, [plantId, hours, thresholds, onLastTimestamp])

  useEffect(() => { load() }, [load])

  function handleThresholdChange(pid: number, value: number) {
    setThresholds(prev => ({ ...prev, [pid]: value }))
    setPendingLoad(true)
  }

  const lastTs    = summary?.last_ts ?? (tsData.length > 0 ? tsData[tsData.length - 1].ts : null)
  const probColor = summary?.max_fault_proba != null
    ? summary.max_fault_proba > 0.8 ? '#f85149' : summary.max_fault_proba > 0.5 ? '#f59e0b' : '#3fb950'
    : '#3fb950'
  const lastTime  = lastTs ? new Date(lastTs).toLocaleTimeString() : '—'
  const lastDate  = lastTs ? new Date(lastTs).toLocaleDateString() : undefined

  const capFactorNum = (summary?.avg_power != null && capacityKw > 0)
    ? summary.avg_power / capacityKw
    : null
  const capFactor = capFactorNum != null ? `${(capFactorNum * 100).toFixed(1)}%` : '—'
  const capColor  = capFactorNum != null
    ? (capFactorNum > 0.6 ? '#3fb950' : capFactorNum > 0.35 ? '#f59e0b' : '#f85149')
    : undefined

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 flex flex-col gap-6">

      {/* Controls */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '6px' }}
           className="flex flex-wrap items-end gap-4 px-4 py-3">
        <Select
          label="PLANTA" value={plantId} options={PLANTS}
          onChange={v => { setPendingLoad(true); setPlantId(Number(v)); onPlantChange?.(Number(v)) }}
        />
        <Select
          label="PERÍODO" value={hours}
          options={[
            { label: '24 h',    value: 24    },
            { label: '48 h',    value: 48    },
            { label: '7 días',  value: 168   },
            { label: '30 días', value: 720   },
            { label: '6 meses', value: 4380  },
            { label: 'Todo',    value: 11000 },
          ]}
          onChange={v => { setPendingLoad(true); setHours(Number(v)) }}
        />

        <ThresholdSlider plantId={plantId} thresholds={thresholds} onChange={handleThresholdChange} />

        <button
          onClick={load} disabled={state === 'loading'}
          style={{
            background: state === 'loading' ? 'var(--surface-2)' : 'var(--solar-dim)',
            border: '1px solid', borderColor: state === 'loading' ? 'var(--border)' : '#f59e0b88',
            color: state === 'loading' ? 'var(--text-dim)' : '#f59e0b',
            borderRadius: '4px', padding: '5px 16px', fontSize: '0.7rem',
            fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.08em',
            cursor: state === 'loading' ? 'not-allowed' : 'pointer',
          }}
        >
          {state === 'loading' ? 'CARGANDO...' : '↻ REFRESH'}
        </button>

        {/* Capacidad de la planta seleccionada */}
        <div style={{ fontSize: '0.6rem', color: 'var(--text-dim)', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ letterSpacing: '0.08em' }}>CAPACIDAD</span>
          <span style={{ color: '#f59e0b', fontFamily: 'JetBrains Mono, monospace', fontWeight: 700 }}>{capacityKw} kW</span>
        </div>

        <div className="ml-auto flex items-center gap-2" style={{ fontSize: '0.6rem', color: 'var(--text-dim)' }}>
          <span style={{
            width: '6px', height: '6px', borderRadius: '50%', display: 'inline-block',
            background: pendingLoad ? '#f59e0b' : state === 'success' ? '#3fb950' : state === 'error' ? '#f85149' : '#6b7f94',
          }} />
          {pendingLoad ? 'APLICANDO...' : state === 'success' ? 'LIVE' : state === 'error' ? 'ERROR' : '—'}
        </div>
      </div>

      {state === 'error'   && error && <ErrorMsg msg={error} />}
      {state === 'loading' && <Spinner />}

      {(state === 'success' || state === 'idle') && summary && (
        <>
          {/* KPI row — 7 tarjetas incluyendo cap. factor */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
            <KpiCard label="POTENCIA PROM."    value={safeFixed(summary.avg_power)} sub="kW" accent="#f59e0b" />
            <KpiCard label="POTENCIA MÁX."     value={safeFixed(summary.max_power)} sub="kW" />
            <KpiCard label="CAP. FACTOR"       value={capFactor} accent={capColor} />
            <KpiCard label="LECTURAS"          value={safeInt(summary.total_readings)} />
            <KpiCard label="FALLAS"            value={safeInt(summary.total_faults)} accent={(summary.total_faults ?? 0) > 0 ? '#f85149' : undefined} />
            <KpiCard label="MÁX. PROB. FALLA"  value={safePct(summary.max_fault_proba)} accent={probColor} />
            <KpiCard label="ÚLTIMO DATO"       value={lastTime} sub={lastDate} />
          </div>

          {/* 4 gráficas en grid 2×2 */}
          {tsData.length > 0 ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <PowerChart            data={tsData} />
              <ResidualFaultChart    data={tsData} />
              <TempIrradianceChart   data={tsData} />
              <PerformanceRatioChart data={tsData} capacityKw={capacityKw} />
            </div>
          ) : (
            <div style={{ border: '1px solid var(--border)', borderRadius: '6px', color: 'var(--text-dim)', fontSize: '0.75rem', padding: '24px', textAlign: 'center' }}>
              SIN DATOS DE SERIES DE TIEMPO EN EL PERÍODO
            </div>
          )}

          {/* Tabla de fallas con ver más/menos */}
          <AlertsTable packages={packages} />
        </>
      )}
    </div>
  )
}