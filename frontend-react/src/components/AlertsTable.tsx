import { useState } from 'react'

interface AlertItem {
  id?: number
  reading_id?: number
  model_version?: string
  expected_power_ac_kw?: number | null
  power_residual_kw?: number | null
  fault_proba?: number | null
  fault_pred?: number | null
  created_at?: string | null
  explanation_text?: string
  top_reasons?: Record<string, number>
}

interface Props {
  alerts: AlertItem[]
}

function safe(val: number | null | undefined, decimals = 2): string {
  if (val === null || val === undefined || isNaN(Number(val))) return '—'
  return Number(val).toFixed(decimals)
}

function safePct(val: number | null | undefined): string {
  if (val === null || val === undefined || isNaN(Number(val))) return '—'
  return `${(Number(val) * 100).toFixed(1)}%`
}

function FaultBadge({ pred }: { pred: number | null | undefined }) {
  if (pred === null || pred === undefined) return <span style={{ color: 'var(--text-dim)' }}>—</span>
  const color = pred === 1 ? '#f85149' : '#3fb950'
  return (
    <span style={{ color, border: `1px solid ${color}`, fontSize: '0.65rem', padding: '1px 6px', borderRadius: '3px' }}>
      {pred === 1 ? 'FALLA' : 'OK'}
    </span>
  )
}

function TopReasons({ reasons }: { reasons: Record<string, number> | null | undefined }) {
  if (!reasons || typeof reasons !== 'object') return null
  const entries = Object.entries(reasons).sort((a, b) => b[1] - a[1])
  if (!entries.length) return null
  return (
    <div style={{ marginTop: '6px', paddingLeft: '8px', borderLeft: '2px solid var(--border)', fontSize: '0.65rem', color: 'var(--text-dim)' }}>
      {entries.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-4">
          <span>{k}</span>
          <span style={{ color: '#f59e0b' }}>{safePct(v)}</span>
        </div>
      ))}
    </div>
  )
}

function AlertRow({ a }: { a: AlertItem }) {
  const [open, setOpen] = useState(false)
  const hasExtra = !!(a.explanation_text) || Object.keys(a.top_reasons ?? {}).length > 0

  return (
    <>
      <tr
        style={{ borderBottom: '1px solid var(--border)', cursor: hasExtra ? 'pointer' : 'default' }}
        onClick={() => hasExtra && setOpen(v => !v)}
      >
        <td className="py-2 pr-3" style={{ color: 'var(--text-dim)', whiteSpace: 'nowrap', fontSize: '0.7rem' }}>
          {a.created_at ? new Date(a.created_at).toLocaleString() : '—'}
        </td>
        <td className="py-2 pr-3" style={{ fontSize: '0.7rem' }}>
          <span style={{ color: (a.fault_proba ?? 0) > 0.8 ? '#f85149' : (a.fault_proba ?? 0) > 0.6 ? '#f59e0b' : '#c9d1d9' }}>
            {safePct(a.fault_proba)}
          </span>
        </td>
        <td className="py-2 pr-3"><FaultBadge pred={a.fault_pred} /></td>
        <td className="py-2 pr-3" style={{ fontSize: '0.7rem' }}>{safe(a.expected_power_ac_kw, 2)}</td>
        <td className="py-2 pr-3" style={{ fontSize: '0.7rem' }}>{safe(a.power_residual_kw, 2)}</td>
        <td className="py-2 pr-3" style={{ fontSize: '0.65rem', color: 'var(--text-dim)' }}>{a.model_version ?? '—'}</td>
        <td className="py-2 text-right" style={{ color: 'var(--text-dim)', fontSize: '0.65rem' }}>
          {hasExtra ? (open ? '▲' : '▼') : ''}
        </td>
      </tr>
      {open && hasExtra && (
        <tr style={{ borderBottom: '1px solid var(--border)' }}>
          <td colSpan={7} style={{ paddingBottom: '12px', paddingLeft: '8px' }}>
            {a.explanation_text && (
              <p style={{ fontSize: '0.7rem', color: 'var(--text-dim)', margin: '6px 0 4px' }}>{a.explanation_text}</p>
            )}
            <TopReasons reasons={a.top_reasons} />
          </td>
        </tr>
      )}
    </>
  )
}

export default function AlertsTable({ alerts }: Props) {
  if (!alerts || alerts.length === 0) {
    return (
      <div
        style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '6px', color: 'var(--text-dim)', fontSize: '0.75rem' }}
        className="p-6 text-center"
      >
        SIN ALERTAS EN EL PERIODO SELECCIONADO
      </div>
    )
  }

  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '6px' }} className="overflow-auto">
      <div className="px-4 pt-4 pb-2" style={{ borderBottom: '1px solid var(--border)' }}>
        <p style={{ fontFamily: 'Syne, sans-serif', fontSize: '0.75rem', color: '#fff', letterSpacing: '0.08em' }}>
          ALERTAS DE FALLA · {alerts.length} EVENTO{alerts.length !== 1 ? 'S' : ''}
        </p>
      </div>
      <table className="w-full" style={{ borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-dim)' }}>
            {['TIMESTAMP', 'PROB. FALLA', 'PRED.', 'POT. ESPERADA (kW)', 'RESIDUAL (kW)', 'MODELO', ''].map(h => (
              <th key={h} className="py-2 pr-3 text-left font-normal px-2" style={{ fontSize: '0.6rem', letterSpacing: '0.06em' }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {alerts.map((a, i) => <AlertRow key={a.id ?? i} a={a} />)}
        </tbody>
      </table>
    </div>
  )
}