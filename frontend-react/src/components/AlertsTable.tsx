import { useState } from 'react'
import type { AlertItem, ExplainResult } from '../types'
import { fetchExplain } from '../lib/api'

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

// ── SHAP Bar Chart ────────────────────────────────────────────────────────────

function ShapBar({ feature, value, maxAbs }: { feature: string; value: number; maxAbs: number }) {
  const pct = Math.abs(value) / maxAbs * 100
  const positive = value > 0
  const color = positive ? '#f85149' : '#3fb950'
  const label = feature.replace(/_/g, ' ')

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr 60px', gap: '8px', alignItems: 'center', marginBottom: '5px' }}>
      <span style={{ fontSize: '0.62rem', color: 'var(--text-dim)', textAlign: 'right', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {label}
      </span>
      <div style={{ background: 'var(--border)', borderRadius: '2px', height: '6px', position: 'relative' }}>
        <div style={{
          position: 'absolute',
          left: positive ? '50%' : `${50 - pct / 2}%`,
          width: `${pct / 2}%`,
          height: '100%',
          background: color,
          borderRadius: '2px',
          transition: 'width 0.4s ease',
        }} />
        <div style={{ position: 'absolute', left: '50%', top: '-2px', width: '1px', height: '10px', background: 'var(--text-dim)', opacity: 0.4 }} />
      </div>
      <span style={{ fontSize: '0.62rem', color, textAlign: 'left' }}>
        {value > 0 ? '+' : ''}{value.toFixed(3)}
      </span>
    </div>
  )
}

// ── XAI Drawer ────────────────────────────────────────────────────────────────

function XAIDrawer({ predictionId, onClose }: { predictionId: number; onClose: () => void }) {
  const [state, setState] = useState<'loading' | 'success' | 'error'>('loading')
  const [result, setResult] = useState<ExplainResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useState(() => {
    fetchExplain(predictionId)
      .then(r => { setResult(r); setState('success') })
      .catch(e => { setError(e.message); setState('error') })
  })

  const maxAbs = result
    ? Math.max(...Object.values(result.top_reasons).map(Math.abs), 0.001)
    : 1

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
          zIndex: 40, backdropFilter: 'blur(2px)',
        }}
      />

      {/* Drawer */}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0,
        width: 'min(480px, 100vw)',
        background: 'var(--surface)',
        borderLeft: '1px solid var(--border)',
        zIndex: 50,
        display: 'flex', flexDirection: 'column',
        overflowY: 'auto',
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 20px',
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: 'var(--surface-2)',
        }}>
          <div>
            <p style={{ fontFamily: 'Syne, sans-serif', fontSize: '0.8rem', color: '#fff', letterSpacing: '0.08em', margin: 0 }}>
              EXPLICACIÓN XAI
            </p>
            <p style={{ fontSize: '0.62rem', color: 'var(--text-dim)', margin: '2px 0 0' }}>
              Predicción #{predictionId}
              {result && <span style={{ marginLeft: '8px', color: result.cached ? '#58a6ff' : '#3fb950' }}>
                {result.cached ? '● CACHE' : '● GENERADO'}
              </span>}
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent', border: '1px solid var(--border)',
              color: 'var(--text-dim)', borderRadius: '4px',
              width: '28px', height: '28px', cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '0.9rem',
            }}
          >✕</button>
        </div>

        {/* Body */}
        <div style={{ padding: '20px', flex: 1 }}>
          {state === 'loading' && (
            <div style={{ color: 'var(--text-dim)', fontSize: '0.7rem', textAlign: 'center', padding: '40px 0' }}>
              <svg className="animate-spin" style={{ display: 'inline', marginRight: '8px' }} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
                <path d="M12 2a10 10 0 0 1 10 10" />
              </svg>
              Consultando modelo...
              <p style={{ fontSize: '0.62rem', marginTop: '8px', opacity: 0.6 }}>
                Primera vez puede tardar ~5s (Ollama)
              </p>
            </div>
          )}

          {state === 'error' && (
            <div style={{ color: '#f85149', fontSize: '0.7rem', border: '1px solid #f8514944', borderRadius: '6px', padding: '12px', background: '#f8514910' }}>
              ERROR: {error}
            </div>
          )}

          {state === 'success' && result && (
            <>
              {/* Prob badge */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: '12px',
                padding: '12px 16px',
                background: 'var(--surface-2)', borderRadius: '6px',
                border: '1px solid var(--border)', marginBottom: '20px',
              }}>
                <div>
                  <p style={{ fontSize: '0.6rem', color: 'var(--text-dim)', margin: 0, letterSpacing: '0.08em' }}>PROB. FALLA</p>
                  <p style={{
                    fontSize: '1.4rem', fontFamily: 'Syne, sans-serif', fontWeight: 700, margin: '2px 0 0',
                    color: (result.fault_proba ?? 0) > 0.8 ? '#f85149' : '#f59e0b',
                  }}>
                    {safePct(result.fault_proba)}
                  </p>
                </div>
                <div style={{ width: '1px', height: '36px', background: 'var(--border)' }} />
                <div>
                  <p style={{ fontSize: '0.6rem', color: 'var(--text-dim)', margin: 0, letterSpacing: '0.08em' }}>BASE ESPERADA</p>
                  <p style={{ fontSize: '0.85rem', fontFamily: 'Syne, sans-serif', color: '#58a6ff', margin: '2px 0 0' }}>
                    {result.expected_value?.toFixed(3) ?? '—'}
                  </p>
                </div>
              </div>

              {/* Explicación Ollama */}
              {result.explanation_text && (
                <div style={{
                  background: 'rgba(88,166,255,0.05)',
                  border: '1px solid rgba(88,166,255,0.2)',
                  borderRadius: '6px', padding: '12px 14px', marginBottom: '20px',
                }}>
                  <p style={{ fontSize: '0.6rem', color: '#58a6ff', letterSpacing: '0.08em', margin: '0 0 6px' }}>
                    🤖 ANÁLISIS (phi3.5)
                  </p>
                  <p style={{ fontSize: '0.72rem', color: 'var(--text)', lineHeight: 1.6, margin: 0 }}>
                    {result.explanation_text}
                  </p>
                </div>
              )}

              {/* SHAP bars */}
              <div>
                <p style={{ fontSize: '0.6rem', color: 'var(--text-dim)', letterSpacing: '0.08em', marginBottom: '12px' }}>
                  CONTRIBUCIÓN DE FEATURES (SHAP)
                </p>
                <div style={{ fontSize: '0.6rem', color: 'var(--text-dim)', display: 'flex', justifyContent: 'space-between', marginBottom: '8px', paddingLeft: '168px' }}>
                  <span style={{ color: '#3fb950' }}>← normal</span>
                  <span style={{ color: '#f85149' }}>falla →</span>
                </div>
                {Object.entries(result.top_reasons).map(([k, v]) => (
                  <ShapBar key={k} feature={k} value={v} maxAbs={maxAbs} />
                ))}
              </div>

              <p style={{ fontSize: '0.6rem', color: 'var(--text-dim)', marginTop: '20px', borderTop: '1px solid var(--border)', paddingTop: '10px' }}>
                Valores SHAP indican cuánto cada feature empuja la predicción hacia falla (+) o normal (−).
              </p>
            </>
          )}
        </div>
      </div>
    </>
  )
}

// ── Alert Row ─────────────────────────────────────────────────────────────────

function AlertRow({ a, onExplain }: { a: AlertItem; onExplain: (id: number) => void }) {
  return (
    <tr style={{ borderBottom: '1px solid var(--border)' }}>
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
      <td className="py-2 text-right">
        {a.id != null && (
          <button
            onClick={() => onExplain(a.id!)}
            style={{
              background: 'rgba(88,166,255,0.08)',
              border: '1px solid rgba(88,166,255,0.3)',
              color: '#58a6ff',
              borderRadius: '3px',
              padding: '2px 8px',
              fontSize: '0.62rem',
              fontFamily: 'JetBrains Mono, monospace',
              cursor: 'pointer',
              letterSpacing: '0.05em',
            }}
          >
            XAI
          </button>
        )}
      </td>
    </tr>
  )
}

// ── AlertsTable ───────────────────────────────────────────────────────────────

interface Props { alerts: AlertItem[] }

export default function AlertsTable({ alerts }: Props) {
  const [explainId, setExplainId] = useState<number | null>(null)

  if (!alerts || alerts.length === 0) {
    return (
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '6px', color: 'var(--text-dim)', fontSize: '0.75rem' }} className="p-6 text-center">
        SIN ALERTAS EN EL PERIODO SELECCIONADO
      </div>
    )
  }

  return (
    <>
      {explainId != null && (
        <XAIDrawer predictionId={explainId} onClose={() => setExplainId(null)} />
      )}

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
            {alerts.map((a, i) => (
              <AlertRow key={a.id ?? i} a={a} onExplain={setExplainId} />
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}