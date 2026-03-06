import { useState, useCallback, useEffect } from 'react'
import type { Summary, TimeseriesItem, FaultPackage } from '../types'
import { fetchSummary, fetchTimeseries, fetchFaultPackages } from '../lib/api'
import { PowerChart, ResidualFaultChart } from '../components/Charts'
import AlertsTable from '../components/AlertsTable'

// ── Null-safety helpers ──────────────────────────────────────────────────────

function safeFixed(val: number | null | undefined, decimals = 2): string {
  if (val === null || val === undefined || isNaN(val)) return '—'
  return val.toFixed(decimals)
}

function safePct(val: number | null | undefined): string {
  if (val === null || val === undefined || isNaN(val)) return '—'
  return `${(val * 100).toFixed(1)}%`
}

function safeInt(val: number | null | undefined): string {
  if (val === null || val === undefined || isNaN(val)) return '—'
  return `${val}`
}

// ── KPI Card ────────────────────────────────────────────────────────────────

interface KpiProps {
  label: string
  value: string
  sub?: string
  accent?: string
}

function KpiCard({ label, value, sub, accent }: KpiProps) {
  return (
    <div style={{ background: 'var(--surface-2)', border: `1px solid ${accent ? accent + '44' : 'var(--border)'}`, borderRadius: '6px', padding: '14px 16px' }}>
      <p style={{ fontSize: '0.6rem', color: 'var(--text-dim)', letterSpacing: '0.1em', marginBottom: '6px' }}>{label}</p>
      <p style={{ fontSize: '1.35rem', fontFamily: 'Syne, sans-serif', fontWeight: 700, color: accent ?? '#fff', lineHeight: 1 }}>{value}</p>
      {sub && <p style={{ fontSize: '0.6rem', color: 'var(--text-dim)', marginTop: '4px' }}>{sub}</p>}
    </div>
  )
}

// ── Controls ────────────────────────────────────────────────────────────────

interface SelectProps {
  label: string
  value: string | number
  options: { label: string; value: string | number }[]
  onChange: (v: string) => void
}

function Select({ label, value, options, onChange }: SelectProps) {
  return (
    <label className="flex flex-col gap-1" style={{ fontSize: '0.6rem', color: 'var(--text-dim)', letterSpacing: '0.08em' }}>
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          borderRadius: '4px',
          color: '#c9d1d9',
          padding: '5px 8px',
          fontSize: '0.75rem',
          fontFamily: 'JetBrains Mono, monospace',
          outline: 'none',
          cursor: 'pointer',
        }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  )
}

// ── Loading / Error helpers ──────────────────────────────────────────────────

function Spinner() {
  return (
    <div className="flex items-center justify-center py-16" style={{ color: 'var(--text-dim)', fontSize: '0.7rem' }}>
      <svg className="animate-spin mr-2" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
        <path d="M12 2a10 10 0 0 1 10 10" />
      </svg>
      CARGANDO...
    </div>
  )
}

function ErrorMsg({ msg }: { msg: string }) {
  return (
    <div style={{ border: '1px solid #f8514944', borderRadius: '6px', color: '#f85149', fontSize: '0.7rem', background: '#f8514910' }} className="p-4">
      ERROR: {msg}
    </div>
  )
}

// ── Dashboard ────────────────────────────────────────────────────────────────

type LoadState = 'idle' | 'loading' | 'success' | 'error'

interface DashboardProps {
  onLastTimestamp?: (ts: string | null) => void
}

export default function Dashboard({ onLastTimestamp }: DashboardProps) {
  const [plantId, setPlantId] = useState(1)
  const [hours, setHours] = useState(11000)
  const [minProba, setMinProba] = useState(0.3)

  const [state, setState] = useState<LoadState>('idle')
  const [error, setError] = useState<string | null>(null)

  const [summary, setSummary] = useState<Summary | null>(null)
  const [tsData, setTsData] = useState<TimeseriesItem[]>([])
  const [packages, setPackages] = useState<FaultPackage[]>([])


  const [pendingLoad, setPendingLoad] = useState(false)

  const load = useCallback(async () => {
    setPendingLoad(false)
    setState('loading')
    setError(null)
    try {
      const [s, ts, al] = await Promise.all([
        fetchSummary(plantId, hours),
        fetchTimeseries(plantId, hours),
        fetchFaultPackages(plantId, hours, minProba),
      ])
      setSummary(s)
      setTsData(Array.isArray(ts) ? ts : [])
      setPackages(Array.isArray(al) ? al : [])
      const lastTs = s.last_ts ?? (Array.isArray(ts) && ts.length > 0 ? ts[ts.length - 1].ts : null)
      onLastTimestamp?.(lastTs)
      setState('success')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setState('error')
    }
  }, [plantId, hours, minProba, onLastTimestamp])

  useEffect(() => { load() }, [load])

  // Derivar last_ts del último item de la serie si no viene en summary
  const lastTs = summary?.last_ts ?? (tsData.length > 0 ? tsData[tsData.length - 1].ts : null)

  const probColor = summary?.max_fault_proba != null
    ? summary.max_fault_proba > 0.8 ? '#f85149' : summary.max_fault_proba > 0.5 ? '#f59e0b' : '#3fb950'
    : '#3fb950'

  const lastTime = lastTs ? new Date(lastTs).toLocaleTimeString() : '—'
  const lastDate = lastTs ? new Date(lastTs).toLocaleDateString() : undefined

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 flex flex-col gap-6">

      {/* ── Controls bar ── */}
      <div
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '6px' }}
        className="flex flex-wrap items-end gap-4 px-4 py-3"
      >
        <Select
          label="PLANTA"
          value={plantId}
          options={[
            { label: 'Planta 1 – Caribe (Barranquilla)',  value: 1 },
            { label: 'Planta 2 – Andina (Bogotá)',        value: 2 },
            { label: 'Planta 3 – Paisa (Medellín)',       value: 3 },
            { label: 'Planta 4 – Valle (Cali)',           value: 4 },
            { label: 'Planta 5 – Llanos (Villavicencio)', value: 5 },
            { label: 'Planta 6 – Guajira (Riohacha)',     value: 6 },
            { label: 'Planta 7 – Sierra Nevada',          value: 7 },
            { label: 'Planta 8 – Boyacá (Tunja)',         value: 8 },
          ]}
          onChange={(v) => { setPendingLoad(true); setPlantId(Number(v)) }}
        />
        <Select
          label="PERÍODO"
          value={hours}
          options={[
            { label: '24 h',    value: 24 },
            { label: '48 h',    value: 48 },
            { label: '7 días',  value: 168 },
            { label: '30 días', value: 720 },
            { label: '6 meses', value: 4380 },
            { label: 'Todo',    value: 11000 },
          ]}
          onChange={(v) => { setPendingLoad(true); setHours(Number(v)) }}
        />
        <Select
          label="MIN. PROB. FALLA"
          value={minProba}
          options={[
            { label: '≥ 30%', value: 0.3 },
            { label: '≥ 60%', value: 0.6 },
            { label: '≥ 80%', value: 0.8 },
          ]}
          onChange={(v) => { setPendingLoad(true); setMinProba(Number(v)) }}
        />

        <button
          onClick={load}
          disabled={state === 'loading'}
          style={{
            background: state === 'loading' ? 'var(--surface-2)' : 'var(--solar-dim)',
            border: '1px solid',
            borderColor: state === 'loading' ? 'var(--border)' : '#f59e0b88',
            color: state === 'loading' ? 'var(--text-dim)' : '#f59e0b',
            borderRadius: '4px',
            padding: '5px 16px',
            fontSize: '0.7rem',
            fontFamily: 'JetBrains Mono, monospace',
            letterSpacing: '0.08em',
            cursor: state === 'loading' ? 'not-allowed' : 'pointer',
          }}
        >
          {state === 'loading' ? 'CARGANDO...' : '↻ REFRESH'}
        </button>

        <div className="ml-auto flex items-center gap-2" style={{ fontSize: '0.6rem', color: 'var(--text-dim)' }}>
          <span style={{
            width: '6px', height: '6px', borderRadius: '50%',
            background: pendingLoad ? '#f59e0b' : state === 'success' ? '#3fb950' : state === 'error' ? '#f85149' : '#6b7f94',
            display: 'inline-block',
          }} />
          {pendingLoad ? 'APLICANDO...' : state === 'success' ? 'LIVE' : state === 'error' ? 'ERROR' : '—'}
        </div>
      </div>

      {/* ── Error ── */}
      {state === 'error' && error && <ErrorMsg msg={error} />}

      {/* ── Loading ── */}
      {state === 'loading' && <Spinner />}

      {/* ── Content ── */}
      {(state === 'success' || state === 'idle') && summary && (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <KpiCard
              label="POTENCIA PROM."
              value={safeFixed(summary.avg_power, 2)}
              sub="kW"
              accent="#f59e0b"
            />
            <KpiCard
              label="POTENCIA MÁX."
              value={safeFixed(summary.max_power, 2)}
              sub="kW"
            />
            <KpiCard
              label="LECTURAS"
              value={safeInt(summary.total_readings)}
            />
            <KpiCard
              label="FALLAS"
              value={safeInt(summary.total_faults)}              // ← corregido
              accent={(summary.total_faults ?? 0) > 0 ? '#f85149' : undefined}
            />
            <KpiCard
              label="MAX PROB. FALLA"
              value={safePct(summary.max_fault_proba)}
              accent={probColor}
            />
            <KpiCard
              label="ÚLTIMO DATO"
              value={lastTime}
              sub={lastDate}
            />
          </div>

          {/* Charts */}
          {tsData.length > 0 ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <PowerChart data={tsData} />
              <ResidualFaultChart data={tsData} />
            </div>
          ) : (
            <div style={{ border: '1px solid var(--border)', borderRadius: '6px', color: 'var(--text-dim)', fontSize: '0.75rem' }} className="p-6 text-center">
              SIN DATOS DE SERIES DE TIEMPO EN EL PERIODO
            </div>
          )}

          {/* Alerts */}
          <AlertsTable packages={packages} />
        </>
      )}
    </div>
  )
}