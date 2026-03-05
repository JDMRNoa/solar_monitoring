import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts'
import type { TimeseriesItem } from '../types'

interface Props {
  data: TimeseriesItem[]
}

function fmtTime(ts: string) {
  const d = new Date(ts)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const TOOLTIP_STYLE = {
  backgroundColor: '#0d1117',
  border: '1px solid #1e2d3d',
  borderRadius: '4px',
  fontSize: '0.7rem',
  fontFamily: 'JetBrains Mono, monospace',
  color: '#c9d1d9',
}

export function PowerChart({ data }: Props) {
  const hasExpected = data.some(d => d.expected_power_ac_kw != null)
  const hasResidual = data.some(d => d.residual_kw != null)
  const hasFaultProba = data.some(d => d.fault_proba != null)

  const chartData = data.map(d => ({
    ts: fmtTime(d.ts),
    'Potencia Real (kW)': d.power_ac_kw ?? null,
    ...(hasExpected ? { 'Potencia Esperada (kW)': d.expected_power_ac_kw ?? null } : {}),
  }))

  return (
    <div
      style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '6px' }}
      className="p-4"
    >
      <p style={{ fontFamily: 'Syne, sans-serif', fontSize: '0.75rem', color: '#fff', letterSpacing: '0.08em', marginBottom: '1rem' }}>
        POTENCIA AC{hasExpected ? ' — REAL vs ESPERADA' : ''}
      </p>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={chartData} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="ts" tick={{ fontSize: 9, fill: '#6b7f94', fontFamily: 'JetBrains Mono, monospace' }} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 9, fill: '#6b7f94', fontFamily: 'JetBrains Mono, monospace' }} />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Legend wrapperStyle={{ fontSize: '0.65rem', fontFamily: 'JetBrains Mono, monospace' }} />
          <Line type="monotone" dataKey="Potencia Real (kW)" stroke="#f59e0b" dot={false} strokeWidth={1.5} connectNulls={false} />
          {hasExpected && (
            <Line type="monotone" dataKey="Potencia Esperada (kW)" stroke="#58a6ff" dot={false} strokeWidth={1.5} strokeDasharray="4 2" connectNulls={false} />
          )}
        </LineChart>
      </ResponsiveContainer>

      {/* Info de campos no disponibles */}
      {(!hasResidual || !hasFaultProba) && (
        <p style={{ fontSize: '0.6rem', color: 'var(--text-dim)', marginTop: '8px', borderTop: '1px solid var(--border)', paddingTop: '6px' }}>
          {!hasResidual && !hasFaultProba
            ? '⚠ residual_kw y fault_proba no disponibles en este endpoint'
            : !hasResidual
            ? '⚠ residual_kw no disponible'
            : '⚠ fault_proba no disponible'}
        </p>
      )}
    </div>
  )
}

export function ResidualFaultChart({ data }: Props) {
  const hasResidual = data.some(d => d.residual_kw != null)
  const hasFaultProba = data.some(d => d.fault_proba != null)

  if (!hasResidual && !hasFaultProba) {
    return (
      <div
        style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '6px' }}
        className="p-4 flex flex-col justify-center items-center gap-2"
      >
        <p style={{ fontFamily: 'Syne, sans-serif', fontSize: '0.75rem', color: '#fff', letterSpacing: '0.08em' }}>
          RESIDUAL & PROB. FALLA
        </p>
        <p style={{ fontSize: '0.7rem', color: 'var(--text-dim)', textAlign: 'center' }}>
          El endpoint <code style={{ color: '#f59e0b' }}>/dashboard/timeseries</code> no retorna
          <br /><code style={{ color: '#58a6ff' }}>residual_kw</code> ni <code style={{ color: '#f85149' }}>fault_proba</code>
        </p>
        <p style={{ fontSize: '0.65rem', color: 'var(--text-dim)' }}>
          Estos datos estarán disponibles cuando el backend los incluya.
        </p>
      </div>
    )
  }

  const chartData = data.map(d => ({
    ts: fmtTime(d.ts),
    ...(hasResidual ? { 'Residual (kW)': d.residual_kw ?? null } : {}),
    ...(hasFaultProba ? { 'Prob. Falla': d.fault_proba ?? null } : {}),
  }))

  return (
    <div
      style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '6px' }}
      className="p-4"
    >
      <p style={{ fontFamily: 'Syne, sans-serif', fontSize: '0.75rem', color: '#fff', letterSpacing: '0.08em', marginBottom: '1rem' }}>
        RESIDUAL & PROBABILIDAD DE FALLA
      </p>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={chartData} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="ts" tick={{ fontSize: 9, fill: '#6b7f94', fontFamily: 'JetBrains Mono, monospace' }} interval="preserveStartEnd" />
          {hasResidual && <YAxis yAxisId="left" tick={{ fontSize: 9, fill: '#6b7f94', fontFamily: 'JetBrains Mono, monospace' }} />}
          {hasFaultProba && <YAxis yAxisId="right" orientation="right" domain={[0, 1]} tick={{ fontSize: 9, fill: '#6b7f94', fontFamily: 'JetBrains Mono, monospace' }} />}
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Legend wrapperStyle={{ fontSize: '0.65rem', fontFamily: 'JetBrains Mono, monospace' }} />
          {hasFaultProba && <ReferenceLine yAxisId="right" y={0.6} stroke="#f85149" strokeDasharray="4 2" strokeWidth={1} />}
          {hasResidual && <Line yAxisId="left" type="monotone" dataKey="Residual (kW)" stroke="#3fb950" dot={false} strokeWidth={1.5} connectNulls={false} />}
          {hasFaultProba && <Line yAxisId="right" type="monotone" dataKey="Prob. Falla" stroke="#f85149" dot={false} strokeWidth={1.5} connectNulls={false} />}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}