import { useState, useEffect } from 'react'
import type { FaultPackage, ExplainResult } from '../types'
import { fetchExplain } from '../lib/api'

const INITIAL_ROWS = 5

// ── Formatters ────────────────────────────────────────────────────────────────

function safe(val: number | null | undefined, d = 2) {
  if (val == null || isNaN(Number(val))) return '—'
  return Number(val).toFixed(d)
}
function safePct(val: number | null | undefined) {
  if (val == null || isNaN(Number(val))) return '—'
  return `${(Number(val) * 100).toFixed(1)}%`
}
function probaColor(p: number | null | undefined) {
  if (!p) return '#6b7f94'
  return p > 0.8 ? '#f85149' : p > 0.6 ? '#f59e0b' : '#c9d1d9'
}
function fmtTs(ts: string | null | undefined) {
  if (!ts) return '—'
  return new Date(ts).toLocaleString('es-CO', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
function fmtDur(min: number) {
  if (min < 60) return `${min} min`
  const h = Math.floor(min / 60), m = min % 60
  return m ? `${h}h ${m}min` : `${h}h`
}

// ── Fault type palette ────────────────────────────────────────────────────────

const FAULT_COLORS: Record<string, string> = {
  inverter_derate: '#f59e0b',
  string_fault: '#f85149',
  grid_disconnect: '#ef4444',
  mppt_failure: '#fb923c',
  partial_shading: '#60a5fa',
  panel_soiling: '#a78bfa',
  pid_effect: '#e879f9',
  sensor_flatline: '#94a3b8',
}
const FAULT_LABELS: Record<string, string> = {
  inverter_derate: 'Inverter Derate',
  string_fault: 'String Fault',
  grid_disconnect: 'Grid Disconnect',
  mppt_failure: 'MPPT Failure',
  partial_shading: 'Partial Shading',
  panel_soiling: 'Panel Soiling',
  pid_effect: 'PID Effect',
  sensor_flatline: 'Sensor Flatline',
}

function FaultBadge({ type, confidence }: { type: string | null; confidence?: number | null }) {
  if (!type) return <span style={{ color: 'var(--text-dim)', fontSize: '0.62rem' }}>—</span>
  const color = FAULT_COLORS[type] ?? '#6b7f94'
  const label = FAULT_LABELS[type] ?? type
  return (
    <div>
      <span style={{
        display: 'inline-block', fontSize: '0.60rem',
        fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.04em',
        color, border: `1px solid ${color}55`, background: `${color}11`,
        borderRadius: '4px', padding: '2px 7px',
      }}>
        {label.toUpperCase()}
      </span>
      {confidence != null && (
        <div style={{ fontSize: '0.56rem', color: 'var(--text-dim)', marginTop: '3px' }}>
          {(confidence * 100).toFixed(0)}% conf.
        </div>
      )}
    </div>
  )
}

// ── SHAP Bar ──────────────────────────────────────────────────────────────────

function ShapBar({ feature, value, maxAbs }: { feature: string; value: number; maxAbs: number }) {
  const pct = Math.abs(value) / maxAbs * 100
  const pos = value > 0
  const color = pos ? '#f85149' : '#3fb950'
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr 60px', gap: '8px', alignItems: 'center', marginBottom: '5px' }}>
      <span style={{ fontSize: '0.62rem', color: 'var(--text-dim)', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {feature.replace(/_/g, ' ')}
      </span>
      <div style={{ background: 'var(--border)', borderRadius: '2px', height: '6px', position: 'relative' }}>
        <div style={{ position: 'absolute', left: pos ? '50%' : `${50 - pct / 2}%`, width: `${pct / 2}%`, height: '100%', background: color, borderRadius: '2px', transition: 'width 0.4s ease' }} />
        <div style={{ position: 'absolute', left: '50%', top: '-2px', width: '1px', height: '10px', background: 'var(--text-dim)', opacity: 0.4 }} />
      </div>
      <span style={{ fontSize: '0.62rem', color }}>{value > 0 ? '+' : ''}{value.toFixed(3)}</span>
    </div>
  )
}

// ── XAI Drawer ────────────────────────────────────────────────────────────────

function XAIDrawer({ pkg, onClose }: { pkg: FaultPackage; onClose: () => void }) {
  const [state, setState] = useState<'loading' | 'success' | 'error'>('loading')
  const [result, setResult] = useState<ExplainResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchExplain(pkg.representative_id)
      .then(r => { setResult(r); setState('success') })
      .catch(e => { setError(e.message); setState('error') })
  }, [pkg.representative_id])

  const maxAbs = result ? Math.max(...Object.values(result.top_reasons).map(Math.abs), 0.001) : 1
  const fc = result?.inferred_fault_type ? (FAULT_COLORS[result.inferred_fault_type] ?? '#6b7f94') : '#6b7f94'

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 40, backdropFilter: 'blur(2px)' }} />
      <div style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 'min(520px, 100vw)', background: 'var(--surface)', borderLeft: '1px solid var(--border)', zIndex: 50, display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>

        {/* Header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', background: 'var(--surface-2)' }}>
          <div>
            <p style={{ fontFamily: 'Syne, sans-serif', fontSize: '0.8rem', color: '#fff', letterSpacing: '0.08em', margin: 0 }}>EXPLICACIÓN XAI</p>
            <p style={{ fontSize: '0.62rem', color: 'var(--text-dim)', margin: '3px 0 0' }}>
              {pkg.reading_count} lectura{pkg.reading_count !== 1 ? 's' : ''} consecutivas
              {pkg.duration_minutes > 0 && ` · ${fmtDur(pkg.duration_minutes)}`}
            </p>
            <p style={{ fontSize: '0.6rem', color: 'var(--text-dim)', margin: '2px 0 0' }}>
              {fmtTs(pkg.start_ts)}{pkg.start_ts !== pkg.end_ts ? ` → ${fmtTs(pkg.end_ts)}` : ''}
            </p>
            {result && <span style={{ marginTop: '4px', display: 'inline-block', fontSize: '0.6rem', color: result.cached ? '#58a6ff' : '#3fb950' }}>{result.cached ? '● CACHE' : '● GENERADO'}</span>}
          </div>
          <button onClick={onClose} style={{ background: 'transparent', border: '1px solid var(--border)', color: 'var(--text-dim)', borderRadius: '4px', width: '28px', height: '28px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.9rem', flexShrink: 0 }}>✕</button>
        </div>

        {/* Body */}
        <div style={{ padding: '20px', flex: 1, display: 'flex', flexDirection: 'column', gap: '16px' }}>

          {state === 'loading' && (
            <div style={{ color: 'var(--text-dim)', fontSize: '0.7rem', textAlign: 'center', padding: '40px 0' }}>
              <svg className="animate-spin" style={{ display: 'inline', marginRight: '8px' }} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" strokeOpacity="0.25" /><path d="M12 2a10 10 0 0 1 10 10" />
              </svg>
              Consultando modelo...
              <p style={{ fontSize: '0.62rem', marginTop: '8px', opacity: 0.6 }}>Primera vez ~5s (Ollama)</p>
            </div>
          )}

          {state === 'error' && (
            <div style={{ color: '#f85149', fontSize: '0.7rem', border: '1px solid #f8514944', borderRadius: '6px', padding: '12px', background: '#f8514910' }}>ERROR: {error}</div>
          )}

          {state === 'success' && result && (
            <>
              {/* Métricas */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px' }}>
                {[
                  { label: 'MÁX. PROB.', value: result.fault_proba != null ? safePct(result.fault_proba) : '—', color: (result.fault_proba ?? 0) > 0.8 ? '#f85149' : '#f59e0b' },
                  { label: 'LECTURAS', value: String(pkg.reading_count), color: '#f59e0b', sub: 'consecutivas' },
                  { label: 'DURACIÓN', value: pkg.duration_minutes > 0 ? fmtDur(pkg.duration_minutes) : '—', color: '#fff' },
                ].map(m => (
                  <div key={m.label} style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '6px', padding: '10px 12px' }}>
                    <p style={{ fontSize: '0.55rem', color: 'var(--text-dim)', margin: 0, letterSpacing: '0.08em' }}>{m.label}</p>
                    <p style={{ fontSize: '1.2rem', fontFamily: 'Syne, sans-serif', fontWeight: 700, margin: '2px 0 0', color: m.color }}>{m.value}</p>
                    {'sub' in m && m.sub && <p style={{ fontSize: '0.55rem', color: 'var(--text-dim)', margin: '2px 0 0' }}>{m.sub}</p>}
                  </div>
                ))}
              </div>

              {/* Tipo inferido */}
              {result.fault_type_label && (
                <div style={{ background: `${fc}0d`, border: `1px solid ${fc}33`, borderRadius: '6px', padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: fc, flexShrink: 0 }} />
                    <div>
                      <p style={{ fontSize: '0.55rem', color: 'var(--text-dim)', margin: 0, letterSpacing: '0.08em' }}>
                        TIPO INFERIDO · {result.fault_type_source === 'model' ? 'CLASIFICADOR ML' : 'REGLAS FÍSICAS'}
                      </p>
                      <p style={{ fontSize: '0.82rem', fontFamily: 'Syne, sans-serif', color: fc, margin: '2px 0 0', fontWeight: 600 }}>
                        {result.fault_type_label}
                      </p>
                    </div>
                  </div>
                  {result.fault_type_confidence != null && (
                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      <p style={{ fontSize: '0.55rem', color: 'var(--text-dim)', margin: 0, letterSpacing: '0.08em' }}>CONFIANZA</p>
                      <p style={{ fontSize: '0.9rem', fontFamily: 'Syne, sans-serif', color: fc, margin: '2px 0 0', fontWeight: 700 }}>{(result.fault_type_confidence * 100).toFixed(0)}%</p>
                    </div>
                  )}
                </div>
              )}

              {/* Análisis */}
              {result.analysis_text && (
                <div style={{ background: 'rgba(88,166,255,0.05)', border: '1px solid rgba(88,166,255,0.2)', borderRadius: '6px', padding: '12px 14px' }}>
                  <p style={{ fontSize: '0.6rem', color: '#58a6ff', letterSpacing: '0.08em', margin: '0 0 6px' }}>ANÁLISIS</p>
                  <p style={{ fontSize: '0.72rem', color: 'var(--text)', lineHeight: 1.6, margin: 0 }}>{result.analysis_text}</p>
                </div>
              )}

              {/* Recomendación */}
              {result.recommendation_text && (
                <div style={{ background: 'rgba(63,185,80,0.05)', border: '1px solid rgba(63,185,80,0.25)', borderRadius: '6px', padding: '12px 14px' }}>
                  <p style={{ fontSize: '0.6rem', color: '#3fb950', letterSpacing: '0.08em', margin: '0 0 6px' }}>RECOMENDACIÓN</p>
                  <p style={{ fontSize: '0.72rem', color: 'var(--text)', lineHeight: 1.6, margin: 0 }}>{result.recommendation_text}</p>
                </div>
              )}

              {/* SHAP */}
              <div>
                <p style={{ fontSize: '0.6rem', color: 'var(--text-dim)', letterSpacing: '0.08em', marginBottom: '12px' }}>CONTRIBUCIÓN DE VARIABLES (SHAP)</p>
                <div style={{ fontSize: '0.6rem', color: 'var(--text-dim)', display: 'flex', justifyContent: 'space-between', marginBottom: '8px', paddingLeft: '168px' }}>
                  <span style={{ color: '#3fb950' }}>← normal</span>
                  <span style={{ color: '#f85149' }}>falla →</span>
                </div>
                {Object.entries(result.top_reasons).map(([k, v]) => <ShapBar key={k} feature={k} value={v} maxAbs={maxAbs} />)}
              </div>

              <p style={{ fontSize: '0.58rem', color: 'var(--text-dim)', borderTop: '1px solid var(--border)', paddingTop: '10px', margin: 0 }}>
                Inferido por {result.fault_type_source === 'model' ? 'clasificador ML' : 'reglas físicas'} · pred. #{result.prediction_id}
              </p>
            </>
          )}
        </div>
      </div>
    </>
  )
}

// ── Package Row ───────────────────────────────────────────────────────────────

function PackageRow({ pkg, onExplain }: { pkg: FaultPackage; onExplain: (p: FaultPackage) => void }) {
  const isPoint = pkg.start_ts === pkg.end_ts || pkg.duration_minutes === 0
  const color = probaColor(pkg.max_fault_proba)

  return (
    <tr style={{ borderBottom: '1px solid var(--border)' }}>
      <td style={{ padding: '10px 12px 10px 16px', fontSize: '0.68rem', minWidth: '150px' }}>
        <div style={{ color: '#c9d1d9' }}>{fmtTs(pkg.start_ts)}</div>
        {!isPoint && <div style={{ color: 'var(--text-dim)', fontSize: '0.6rem', marginTop: '2px' }}>→ {fmtTs(pkg.end_ts)}</div>}
      </td>
      <td style={{ padding: '10px 12px', fontSize: '0.68rem', color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
        {isPoint ? '—' : fmtDur(pkg.duration_minutes)}
        {pkg.reading_count > 1 && <div style={{ fontSize: '0.58rem', marginTop: '2px' }}>{pkg.reading_count} lecturas</div>}
      </td>
      <td style={{ padding: '10px 12px' }}>
        <div style={{ fontSize: '0.78rem', fontWeight: 600, color }}>{safePct(pkg.max_fault_proba)}</div>
        <div style={{ marginTop: '4px', height: '3px', borderRadius: '2px', background: 'var(--border)', width: '60px' }}>
          <div style={{ height: '100%', borderRadius: '2px', background: color, width: `${(pkg.max_fault_proba ?? 0) * 100}%` }} />
        </div>
      </td>
      {/* Tipo inferido por ML — no ground truth del simulador */}
      <td style={{ padding: '10px 12px' }}>
        <FaultBadge type={pkg.fault_type_pred ?? null} confidence={pkg.fault_type_proba ?? null} />
      </td>
      <td style={{ padding: '10px 12px', fontSize: '0.7rem' }}>{safe(pkg.representative_expected_kw)}</td>
      <td style={{ padding: '10px 12px', fontSize: '0.7rem', color: (pkg.representative_residual_kw ?? 0) < 0 ? '#f85149' : 'var(--text)' }}>
        {safe(pkg.representative_residual_kw)}
      </td>
      <td style={{ padding: '10px 16px 10px 0', textAlign: 'right' }}>
        <button
          onClick={() => onExplain(pkg)}
          style={{ background: 'rgba(88,166,255,0.08)', border: '1px solid rgba(88,166,255,0.3)', color: '#58a6ff', borderRadius: '3px', padding: '3px 10px', fontSize: '0.62rem', fontFamily: 'JetBrains Mono, monospace', cursor: 'pointer', letterSpacing: '0.05em' }}
        >
          XAI
        </button>
      </td>
    </tr>
  )
}

// ── AlertsTable ───────────────────────────────────────────────────────────────

interface Props { packages: FaultPackage[] }

export default function AlertsTable({ packages }: Props) {
  const [active, setActive] = useState<FaultPackage | null>(null)
  const [expanded, setExpanded] = useState(false)

  if (!packages || packages.length === 0) {
    return (
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '6px', color: 'var(--text-dim)', fontSize: '0.75rem', padding: '24px', textAlign: 'center' }}>
        SIN FALLAS DETECTADAS EN EL PERÍODO SELECCIONADO
      </div>
    )
  }

  const totalReadings = packages.reduce((s, p) => s + p.reading_count, 0)
  const visible = expanded ? packages : packages.slice(0, INITIAL_ROWS)
  const hidden = packages.length - INITIAL_ROWS

  return (
    <>
      {active && <XAIDrawer pkg={active} onClose={() => setActive(null)} />}

      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '6px', overflow: 'hidden' }}>

        {/* Header */}
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px' }}>
            <p style={{ fontFamily: 'Syne, sans-serif', fontSize: '0.75rem', color: '#fff', letterSpacing: '0.08em', margin: 0 }}>EVENTOS DE FALLA</p>
            <span style={{ fontSize: '0.62rem', color: 'var(--text-dim)' }}>
              {packages.length} evento{packages.length !== 1 ? 's' : ''} · {totalReadings} lectura{totalReadings !== 1 ? 's' : ''}
            </span>
          </div>
          <span style={{ fontSize: '0.58rem', color: 'var(--text-dim)', fontStyle: 'italic' }}>
            Tipo inferido por ML — no ground truth
          </span>
        </div>

        {/* Tabla */}
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-dim)' }}>
                {['INICIO → FIN', 'DURACIÓN', 'MÁX. PROB.', 'TIPO INFERIDO', 'P. ESPERADA (kW)', 'RESIDUAL (kW)', ''].map(h => (
                  <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 'normal', fontSize: '0.6rem', letterSpacing: '0.06em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.map((pkg, i) => (
                <PackageRow key={`${pkg.start_ts}-${i}`} pkg={pkg} onExplain={setActive} />
              ))}
            </tbody>
          </table>
        </div>

        {/* Ver más / menos */}
        {packages.length > INITIAL_ROWS && (
          <div style={{ borderTop: '1px solid var(--border)', padding: '10px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '0.62rem', color: 'var(--text-dim)' }}>
              {expanded
                ? `Mostrando todos los ${packages.length} eventos`
                : `${INITIAL_ROWS} de ${packages.length} — ${hidden} oculto${hidden !== 1 ? 's' : ''}`}
            </span>
            <button
              onClick={() => setExpanded(e => !e)}
              style={{ background: 'transparent', border: '1px solid var(--border)', color: '#58a6ff', borderRadius: '4px', padding: '4px 14px', fontSize: '0.65rem', fontFamily: 'JetBrains Mono, monospace', cursor: 'pointer', letterSpacing: '0.05em' }}
            >
              {expanded ? 'Ver menos' : `Ver ${hidden} más`}
            </button>
          </div>
        )}
      </div>
    </>
  )
}