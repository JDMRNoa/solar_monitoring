import {
  ResponsiveContainer, LineChart, Line, ComposedChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine,
} from 'recharts'
import type { TimeseriesItem } from '../types'

interface Props { data: TimeseriesItem[] }

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtTime(ts: string) {
  const d = new Date(ts)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const TOOLTIP_STYLE = {
  backgroundColor: '#0d1117', border: '1px solid #1e2d3d',
  borderRadius: '4px', fontSize: '0.7rem',
  fontFamily: 'JetBrains Mono, monospace', color: '#c9d1d9',
}
const TICK    = { fontSize: 9, fill: '#6b7f94', fontFamily: 'JetBrains Mono, monospace' }
const LEGEND  = { fontSize: '0.62rem', fontFamily: 'JetBrains Mono, monospace' }
const MARGIN  = { top: 4, right: 10, left: -10, bottom: 0 }
const H       = 210

function Shell({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '6px', padding: '14px 16px' }}>
      <p style={{ fontFamily: 'Syne, sans-serif', fontSize: '0.72rem', color: '#fff', letterSpacing: '0.08em', margin: '0 0 12px' }}>{title}</p>
      {children}
      {note && <p style={{ fontSize: '0.58rem', color: 'var(--text-dim)', marginTop: '8px', borderTop: '1px solid var(--border)', paddingTop: '6px', margin: '8px 0 0' }}>{note}</p>}
    </div>
  )
}

function NoData({ label }: { label: string }) {
  return (
    <div style={{ height: H, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <p style={{ fontSize: '0.7rem', color: 'var(--text-dim)', fontStyle: 'italic' }}>{label}</p>
    </div>
  )
}

// ── 1. Potencia Real vs Esperada ──────────────────────────────────────────────

export function PowerChart({ data }: Props) {
  const hasExpected = data.some(d => d.expected_power_ac_kw != null)
  const chartData   = data.map(d => ({
    ts:              fmtTime(d.ts),
    'Real (kW)':     d.power_ac_kw       ?? null,
    'Esperada (kW)': d.expected_power_ac_kw ?? null,
  }))

  return (
    <Shell title="POTENCIA AC — REAL vs ESPERADA">
      <ResponsiveContainer width="100%" height={H}>
        <LineChart data={chartData} margin={MARGIN}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2d3d" />
          <XAxis dataKey="ts" tick={TICK} interval="preserveStartEnd" />
          <YAxis tick={TICK} />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Legend wrapperStyle={LEGEND} />
          <Line type="monotone" dataKey="Real (kW)"     stroke="#f59e0b" dot={false} strokeWidth={1.5} connectNulls={false} />
          {hasExpected && <Line type="monotone" dataKey="Esperada (kW)" stroke="#58a6ff" dot={false} strokeWidth={1.5} strokeDasharray="4 2" connectNulls={false} />}
        </LineChart>
      </ResponsiveContainer>
    </Shell>
  )
}

// ── 2. Residual + Probabilidad de Falla ──────────────────────────────────────

export function ResidualFaultChart({ data }: Props) {
  const hasRes   = data.some(d => d.power_residual_kw != null)
  const hasProba = data.some(d => d.fault_proba != null)

  if (!hasRes && !hasProba) return (
    <Shell title="RESIDUAL & PROBABILIDAD DE FALLA">
      <NoData label="Sin datos de residual ni probabilidad en este período." />
    </Shell>
  )

  const chartData = data.map(d => ({
    ts:              fmtTime(d.ts),
    'Residual (kW)': d.power_residual_kw ?? null,
    'Prob. Falla':   d.fault_proba       ?? null,
  }))

  return (
    <Shell title="RESIDUAL & PROBABILIDAD DE FALLA">
      <ResponsiveContainer width="100%" height={H}>
        <LineChart data={chartData} margin={MARGIN}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2d3d" />
          <XAxis dataKey="ts" tick={TICK} interval="preserveStartEnd" />
          {hasRes   && <YAxis yAxisId="left"  tick={TICK} />}
          {hasProba && <YAxis yAxisId="right" orientation="right" domain={[0, 1]} tick={TICK} />}
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Legend wrapperStyle={LEGEND} />
          {hasProba && <ReferenceLine yAxisId="right" y={0.6} stroke="#f85149" strokeDasharray="4 2" strokeWidth={1} />}
          {hasRes   && <Line yAxisId="left"  type="monotone" dataKey="Residual (kW)" stroke="#3fb950" dot={false} strokeWidth={1.5} connectNulls={false} />}
          {hasProba && <Line yAxisId="right" type="monotone" dataKey="Prob. Falla"   stroke="#f85149" dot={false} strokeWidth={1.5} connectNulls={false} />}
        </LineChart>
      </ResponsiveContainer>
    </Shell>
  )
}

// ── 3. Temperatura Módulo vs Irradiancia normalizada ──────────────────────────
// Divergencia sostenida detecta: inverter_derate (T sube sin irradiancia),
// partial_shading (irradiancia cae sin que baje temperatura)

export function TempIrradianceChart({ data }: Props) {
  const hasTemp = data.some(d => d.temp_module_c != null)
  const hasIrr  = data.some(d => d.irradiance_wm2 != null)

  if (!hasTemp && !hasIrr) return (
    <Shell title="TEMPERATURA MÓDULO vs IRRADIANCIA">
      <NoData label="Sin datos de temperatura e irradiancia en el endpoint." />
    </Shell>
  )

  const maxIrr = Math.max(...data.map(d => d.irradiance_wm2 ?? 0), 1)
  const chartData = data.map(d => ({
    ts:             fmtTime(d.ts),
    'T. Módulo (°C)':  d.temp_module_c   ?? null,
    'Irrad. norm. (%)': d.irradiance_wm2 != null
      ? Math.round((d.irradiance_wm2 / maxIrr) * 100) : null,
  }))

  return (
    <Shell
      title="TEMPERATURA MÓDULO vs IRRADIANCIA"
      note="Irradiancia normalizada al máx. del período. Temperatura sube sin irradiancia → posible inverter derate. Irradiancia cae sola → sombra."
    >
      <ResponsiveContainer width="100%" height={H}>
        <LineChart data={chartData} margin={MARGIN}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2d3d" />
          <XAxis dataKey="ts" tick={TICK} interval="preserveStartEnd" />
          {hasTemp && <YAxis yAxisId="left"  tick={TICK} unit="°C" />}
          {hasIrr  && <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tick={TICK} unit="%" />}
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Legend wrapperStyle={LEGEND} />
          {hasTemp && <Line yAxisId="left"  type="monotone" dataKey="T. Módulo (°C)"   stroke="#ff7043" dot={false} strokeWidth={1.5} connectNulls={false} />}
          {hasIrr  && <Line yAxisId="right" type="monotone" dataKey="Irrad. norm. (%)" stroke="#ffd600" dot={false} strokeWidth={1.5} strokeDasharray="3 2" connectNulls={false} />}
        </LineChart>
      </ResponsiveContainer>
    </Shell>
  )
}

// ── 4. Performance Ratio (eficiencia de conversión) ───────────────────────────
// PR = (P_ac / capacidad) / (irradiancia / 1000)
// Saludable: 0.70–0.85. Caída sostenida → soiling, degradación, falla de strings.
// Solo puntos diurnos (irradiancia > 50 W/m²) para evitar ruido nocturno.

export function PerformanceRatioChart({ data, capacityKw }: Props & { capacityKw?: number }) {
  const cap     = capacityKw ?? 100
  const hasIrr  = data.some(d => d.irradiance_wm2 != null)
  const hasExp  = data.some(d => d.expected_power_ac_kw != null)

  const chartData = data
    .filter(d => (d.irradiance_wm2 ?? 0) > 50)
    .map(d => {
      const irr  = d.irradiance_wm2 as number
      const real = d.power_ac_kw ?? 0
      const exp  = d.expected_power_ac_kw ?? null
      const pr   = irr > 0 ? (real / cap) / (irr / 1000) : null
      const prEx = (exp != null && irr > 0) ? (exp / cap) / (irr / 1000) : null
      return {
        ts:            fmtTime(d.ts),
        'PR Real':     pr   != null ? Math.min(1.2, +pr.toFixed(3))   : null,
        'PR Esperado': prEx != null ? Math.min(1.2, +prEx.toFixed(3)) : null,
      }
    })

  if (!hasIrr || chartData.length === 0) return (
    <Shell title="PERFORMANCE RATIO">
      <NoData label="Sin irradiancia suficiente para calcular PR." />
    </Shell>
  )

  return (
    <Shell
      title="PERFORMANCE RATIO (EFICIENCIA)"
      note="PR = P_ac / (irradiancia × capacidad). Saludable: 0.70–0.85. Caída sostenida indica soiling, degradación o falla de strings."
    >
      <ResponsiveContainer width="100%" height={H}>
        <ComposedChart data={chartData} margin={MARGIN}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2d3d" />
          <XAxis dataKey="ts" tick={TICK} interval="preserveStartEnd" />
          <YAxis tick={TICK} domain={[0, 1.1]} tickFormatter={v => v.toFixed(2)} />
          <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: any) => typeof v === 'number' ? v.toFixed(3) : v} />
          <Legend wrapperStyle={LEGEND} />
          <ReferenceLine y={0.75} stroke="#3fb950" strokeDasharray="4 2" strokeWidth={1} label={{ value: '0.75 óptimo', fill: '#3fb950', fontSize: 8, position: 'insideTopRight' }} />
          <ReferenceLine y={0.55} stroke="#f59e0b" strokeDasharray="4 2" strokeWidth={1} label={{ value: '0.55 alerta',  fill: '#f59e0b', fontSize: 8, position: 'insideTopRight' }} />
          {hasExp && <Area type="monotone" dataKey="PR Esperado" stroke="#58a6ff" fill="#58a6ff18" strokeWidth={1} strokeDasharray="4 2" dot={false} connectNulls={false} />}
          <Line type="monotone" dataKey="PR Real" stroke="#00d4ff" dot={false} strokeWidth={1.5} connectNulls={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </Shell>
  )
}