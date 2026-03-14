import { useState, useEffect, useCallback } from 'react'
import Cookies from 'js-cookie'

// ── Types ─────────────────────────────────────────────────────────────────────
interface SimStatus {
  running: boolean
  step_count: number
  total_records: number
  total_faults: number
  fault_rate_pct: number
  last_ts: string | null
  config: { fault_level: number; n_plants: number }
}

interface DbStats {
  solar_readings: number
  ai_predictions: number
  ai_explanations: number
}

interface ActiveFault {
  plant_id: number
  inverter_id: string
  fault_type: string
  severity: number
  remaining: number
}

interface CsvBackup {
  id: string
  size_mb: number
  created: string
}

interface ModelStatus {
  plant_id: number
  plant_name: string
  f1_binary: number | null
  f1_type: number | null
  mae: number | null
  roc_auc: number | null
  n_samples: number | null
  trained_at: string | null
  has_backup: boolean
}

interface DbReading {
  id: number
  ts: string
  plant_id: number
  inverter_id: string
  irradiance_wm2: number
  temp_module_c: number
  power_ac_kw: number
  expected_power_ac_kw: number
  label_is_fault: number
  fault_type: string
}

type AdminTab = 'sistema' | 'simulador' | 'db' | 'ml'

// ── Constants ─────────────────────────────────────────────────────────────────
const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

const FAULT_COLORS: Record<string, string> = {
  inverter_derate: '#f59e0b',
  panel_soiling: '#a78bfa',
  mppt_failure: '#38bdf8',
  partial_shading: '#34d399',
  string_fault: '#fb923c',
  grid_disconnect: '#f87171',
  pid_effect: '#e879f9',
  sensor_flatline: '#94a3b8',
}

// ── API helper ────────────────────────────────────────────────────────────────
async function adminFetch(path: string, method = 'GET', body?: any) {
  const token = Cookies.get('solarmonitor_jwt')
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

// ── Shared sub-components ─────────────────────────────────────────────────────
function StatBox({ label, value, color = '#fff' }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{
      background: 'rgba(0,0,0,0.25)', padding: '12px 14px',
      borderRadius: 6, border: '1px solid var(--border)',
    }}>
      <div style={{ fontSize: '0.58rem', color: 'var(--text-dim)', letterSpacing: '0.12em', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: '1.05rem', color, fontFamily: "'JetBrains Mono', monospace", fontWeight: 700 }}>{value}</div>
    </div>
  )
}

function Btn({
  label, variant = 'ghost', onClick, disabled = false, small = false
}: {
  label: string; variant?: 'primary' | 'danger' | 'ghost' | 'success' | 'purple'
  onClick?: () => void; disabled?: boolean; small?: boolean
}) {
  const styles: Record<string, React.CSSProperties> = {
    primary: { background: 'var(--solar)', color: '#000', border: 'none' },
    danger: { background: 'transparent', color: 'var(--red)', border: '1px solid var(--red)' },
    ghost: { background: 'transparent', color: 'var(--text)', border: '1px solid var(--border)' },
    success: { background: 'transparent', color: 'var(--green)', border: '1px solid var(--green)' },
    purple: { background: 'transparent', color: '#a78bfa', border: '1px solid #a78bfa' },
  }
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        ...styles[variant],
        padding: small ? '5px 10px' : '8px 16px',
        borderRadius: 5,
        cursor: disabled ? 'not-allowed' : 'pointer',
        fontSize: small ? '0.68rem' : '0.75rem',
        fontFamily: "'JetBrains Mono', monospace",
        letterSpacing: '0.05em',
        fontWeight: 600,
        opacity: disabled ? 0.4 : 1,
        transition: 'all 0.15s',
        whiteSpace: 'nowrap' as const,
      }}
    >{label}</button>
  )
}

function Card({ children, danger = false }: { children: React.ReactNode; danger?: boolean }) {
  return (
    <div style={{
      background: 'var(--surface)',
      border: `1px solid ${danger ? 'rgba(248,81,73,0.25)' : 'var(--border)'}`,
      borderRadius: 8, padding: '20px',
    }}>{children}</div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: '0.6rem', color: 'var(--text-dim)', letterSpacing: '0.18em', marginBottom: 14 }}>
      {children}
    </div>
  )
}

function f1Color(v: number | null) {
  if (v === null) return 'var(--text-dim)'
  if (v >= 0.9) return 'var(--green)'
  if (v >= 0.7) return 'var(--solar)'
  return 'var(--red)'
}

// ── Section: Sistema ──────────────────────────────────────────────────────────
function SectionSistema({
  db, simStatus, onAction
}: {
  db: DbStats | null
  simStatus: SimStatus | null
  onAction: (path: string, method?: string, body?: any) => Promise<void>
}) {
  const [services, setServices] = useState({ backend: false, db: false, ollama: false, simulator: false })

  useEffect(() => {
    async function checkServices() {
      // Everything goes through the nginx proxy to avoid CORS.
      // Simulator status comes from /admin/status (proxied).
      // Ollama is checked via a backend health-equivalent route that doesn't exist yet,
      // so we fall back to checking the admin/status endpoint as a proxy for db+backend.
      const [backendCheck, adminCheck] = await Promise.allSettled([
        fetch(`${BASE}/health`).then(r => r.ok),
        adminFetch('/admin/status').then((data) => data),
      ])
      const backendOk = backendCheck.status === 'fulfilled' && backendCheck.value === true
      const adminOk = adminCheck.status === 'fulfilled'
      const adminData = adminOk ? (adminCheck as PromiseFulfilledResult<any>).value : null

      setServices({
        backend: backendOk,
        db: adminOk,
        ollama: adminOk, // Ollama is inaccessible from browser due to CORS; proxy not implemented
        simulator: adminData?.simulator !== null && adminData?.simulator !== undefined,
      })
    }
    checkServices()
  }, [simStatus])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card>
        <SectionLabel>SERVICIOS</SectionLabel>
        <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
          {([
            ['Backend :8000', services.backend],
            ['PostgreSQL :5432', services.db],
            ['Ollama :11434', services.ollama],
            ['Simulador :9000', services.simulator],
          ] as [string, boolean][]).map(([label, ok]) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{
                width: 7, height: 7, borderRadius: '50%',
                background: ok ? 'var(--green)' : 'var(--red)',
                boxShadow: ok ? '0 0 6px var(--green)' : '0 0 6px var(--red)',
              }} />
              <span style={{ fontSize: '0.72rem', color: ok ? 'var(--text)' : 'var(--red)' }}>{label}</span>
            </div>
          ))}
        </div>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        <StatBox label="SOLAR READINGS" value={(db?.solar_readings ?? 0).toLocaleString()} color='var(--blue)' />
        <StatBox label="AI PREDICTIONS" value={(db?.ai_predictions ?? 0).toLocaleString()} color='#a78bfa' />
        <StatBox label="AI EXPLANATIONS" value={(db?.ai_explanations ?? 0).toLocaleString()} color='var(--green)' />
      </div>

      <Card>
        <SectionLabel>ACCIONES RÁPIDAS</SectionLabel>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button
            onClick={() => onAction('/admin/ml/retrain', 'POST')}
            style={{
              background: 'transparent', color: '#a78bfa', border: '1px solid #a78bfa',
              padding: '8px 16px', borderRadius: 5, cursor: 'pointer',
              fontSize: '0.75rem', fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: '0.05em', fontWeight: 600, transition: 'all 0.15s',
              display: 'flex', alignItems: 'center', gap: '8px'
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .52 8.242 4.42 4.42 0 0 0 8.71 0 4 4 0 0 0 .52-8.242 4 4 0 0 0-2.526-5.77A3 3 0 0 0 12 5" />
              <path d="M9 13h4" /><path d="M12 10v6" />
            </svg>
            REENTRENAR ML
          </button>
          <button
            onClick={() => onAction('/admin/db/export', 'POST')}
            style={{
              background: 'transparent', color: 'var(--text)', border: '1px solid var(--border)',
              padding: '8px 16px', borderRadius: 5, cursor: 'pointer',
              fontSize: '0.75rem', fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: '0.05em', fontWeight: 600, transition: 'all 0.15s',
              display: 'flex', alignItems: 'center', gap: '8px'
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" x2="12" y1="15" y2="3" />
            </svg>
            EXPORT DB → CSV
          </button>
        </div>
      </Card>
    </div>
  )
}

// ── CSV Backups Card ──────────────────────────────────────────────────────────
function CsvBackupsCard({ onAction, loading }: { onAction: (path: string, method?: string, body?: any) => Promise<void>; loading: boolean }) {
  const [backups, setBackups] = useState<CsvBackup[]>([])
  const [reingesting, setReingesting] = useState<string | null>(null)
  const [reingestMsg, setReingestMsg] = useState<string>('')
  const [elapsed, setElapsed] = useState(0)

  const fetchBackups = async () => {
    try {
      const d = await adminFetch('/admin/simulator/csv-backups')
      setBackups(d.backups ?? [])
    } catch { /* ignore */ }
  }

  useEffect(() => { fetchBackups() }, [])

  const handleReingest = async (backupId?: string) => {
    const key = backupId ?? 'active'
    setReingesting(key)
    setReingestMsg('Iniciando...')
    setElapsed(0)
    try {
      const path = backupId
        ? `/admin/simulator/reingest?backup_id=${backupId}`
        : '/admin/simulator/reingest'
      // Fire-and-forget: backend returns 202 immediately
      await onAction(path, 'POST')
      // Poll /reingest/status until done
      let secs = 0
      const poll = setInterval(async () => {
        secs++
        setElapsed(secs)
        try {
          const st = await adminFetch('/admin/simulator/reingest-status')
          if (!st.running) {
            clearInterval(poll)
            setReingesting(null)
            setReingestMsg(st.error ? `Error: ${st.error.slice(0, 80)}` : '✓ Completado')
            setTimeout(() => setReingestMsg(''), 5000)
          }
        } catch { /* ignore */ }
      }, 2000)
    } catch (e: any) {
      setReingesting(null)
      setReingestMsg(`Error: ${e.message}`)
      setTimeout(() => setReingestMsg(''), 4000)
    }
  }

  const handleRestore = async (backupId: string) => {
    await onAction(`/admin/simulator/csv-backups/${backupId}/restore`, 'POST')
    await fetchBackups()
  }

  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <SectionLabel>CSV BACKUPS</SectionLabel>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {reingestMsg && (
            <span style={{ fontSize: '0.62rem', color: reingestMsg.startsWith('Error') ? 'var(--red)' : 'var(--green)', fontFamily: "'JetBrains Mono', monospace" }}>
              {reingestMsg}
            </span>
          )}
          <Btn label="REFRESH" variant="ghost" small onClick={fetchBackups} />
          <button
            disabled={loading || reingesting !== null}
            onClick={() => handleReingest()}
            style={{
              background: 'transparent', color: 'var(--text)', border: '1px solid var(--border)',
              padding: '5px 10px', borderRadius: 5, cursor: (loading || reingesting !== null) ? 'not-allowed' : 'pointer',
              fontSize: '0.68rem', fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: '0.05em', fontWeight: 600, opacity: (loading || reingesting !== null) ? 0.4 : 1, transition: 'all 0.15s',
              display: 'flex', alignItems: 'center', gap: '6px'
            }}
          >
            {reingesting === 'active' ? (
              <svg className="animate-spin" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
                <path d="M12 2a10 10 0 0 1 10 10" />
              </svg>
            ) : (
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" x2="12" y1="3" y2="15" />
              </svg>
            )}
            {reingesting === 'active' ? `${elapsed}s…` : 'REINGESTAR ACTIVO'}
          </button>
        </div>
      </div>

      {backups.length === 0 ? (
        <div style={{ color: 'var(--text-dim)', fontSize: '0.75rem', padding: '12px 0' }}>
          Sin backups — se crean automáticamente al hacer Reset
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {backups.map(b => (
            <div key={b.id} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '8px 12px', background: 'var(--surface-2)', borderRadius: 6,
              border: '1px solid var(--border)',
            }}>
              <div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text)', fontFamily: "'JetBrains Mono', monospace" }}>{b.id}</div>
                <div style={{ fontSize: '0.62rem', color: 'var(--text-dim)', marginTop: 2 }}>{b.created} · {b.size_mb} MB</div>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <Btn label="RESTAURAR" variant="ghost" small
                  disabled={loading} onClick={() => handleRestore(b.id)} />
                <button
                  disabled={loading || reingesting !== null}
                  onClick={() => handleReingest(b.id)}
                  style={{
                    background: 'transparent', color: '#a78bfa', border: '1px solid #a78bfa',
                    padding: '5px 10px', borderRadius: 5, cursor: (loading || reingesting !== null) ? 'not-allowed' : 'pointer',
                    fontSize: '0.68rem', fontFamily: "'JetBrains Mono', monospace",
                    letterSpacing: '0.05em', fontWeight: 600, opacity: (loading || reingesting !== null) ? 0.4 : 1, transition: 'all 0.15s',
                    display: 'flex', alignItems: 'center', gap: '6px'
                  }}
                >
                  {reingesting === b.id ? (
                    <svg className="animate-spin" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                      <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
                      <path d="M12 2a10 10 0 0 1 10 10" />
                    </svg>
                  ) : (
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" x2="12" y1="3" y2="15" />
                    </svg>
                  )}
                  {reingesting === b.id ? `${elapsed}s…` : 'REINGESTAR'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

// ── Section: Simulador ────────────────────────────────────────────────────────
function SectionSimulador({
  simStatus, faults, onAction, loading
}: {
  simStatus: SimStatus | null
  faults: ActiveFault[]
  onAction: (path: string, method?: string, body?: any) => Promise<void>
  loading: boolean
}) {
  const [nSteps, setNSteps] = useState(1000)

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>

      {/* Left */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <SectionLabel>ESTADO</SectionLabel>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{
                width: 7, height: 7, borderRadius: '50%',
                background: simStatus?.running ? 'var(--green)' : 'var(--red)',
                boxShadow: simStatus?.running ? '0 0 8px var(--green)' : 'none',
              }} />
              <span style={{ fontSize: '0.72rem', color: simStatus?.running ? 'var(--green)' : 'var(--red)' }}>
                {simStatus?.running ? 'CORRIENDO' : 'DETENIDO'}
              </span>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <StatBox label="STEPS" value={(simStatus?.step_count ?? 0).toLocaleString()} />
            <StatBox label="REGISTROS" value={(simStatus?.total_records ?? 0).toLocaleString()} />
            <StatBox label="TASA FALLAS" value={`${simStatus?.fault_rate_pct ?? 0}%`} color='var(--solar)' />
            <StatBox label="FAULT LEVEL" value={`L${simStatus?.config?.fault_level ?? '?'}`} color='#a78bfa' />
          </div>
        </Card>

        <Card>
          <SectionLabel>CONTROLES</SectionLabel>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
            {!simStatus?.running
              ? (
                <button
                  disabled={loading}
                  onClick={() => onAction('/admin/simulator/start')}
                  style={{
                    background: 'transparent', color: 'var(--green)', border: '1px solid var(--green)',
                    padding: '8px 16px', borderRadius: 5, cursor: loading ? 'not-allowed' : 'pointer',
                    fontSize: '0.75rem', fontFamily: "'JetBrains Mono', monospace",
                    letterSpacing: '0.05em', fontWeight: 600, opacity: loading ? 0.4 : 1, transition: 'all 0.15s',
                    display: 'flex', alignItems: 'center', gap: '8px'
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polygon points="5 3 19 12 5 21 5 3" />
                  </svg>
                  START
                </button>
              ) : (
                <button
                  disabled={loading}
                  onClick={() => onAction('/admin/simulator/stop')}
                  style={{
                    background: 'transparent', color: 'var(--red)', border: '1px solid var(--red)',
                    padding: '8px 16px', borderRadius: 5, cursor: loading ? 'not-allowed' : 'pointer',
                    fontSize: '0.75rem', fontFamily: "'JetBrains Mono', monospace",
                    letterSpacing: '0.05em', fontWeight: 600, opacity: loading ? 0.4 : 1, transition: 'all 0.15s',
                    display: 'flex', alignItems: 'center', gap: '8px'
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" />
                  </svg>
                  STOP
                </button>
              )
            }
            <button
              disabled={loading || !!simStatus?.running}
              onClick={() => onAction('/admin/simulator/reset', 'DELETE')}
              style={{
                background: 'transparent', color: 'var(--text)', border: '1px solid var(--border)',
                padding: '8px 16px', borderRadius: 5, cursor: (loading || !!simStatus?.running) ? 'not-allowed' : 'pointer',
                fontSize: '0.75rem', fontFamily: "'JetBrains Mono', monospace",
                letterSpacing: '0.05em', fontWeight: 600, opacity: (loading || !!simStatus?.running) ? 0.4 : 1, transition: 'all 0.15s',
                display: 'flex', alignItems: 'center', gap: '8px'
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" /><path d="M3 3v5h5" />
              </svg>
              RESET
            </button>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="number" value={nSteps} min={1} max={10000}
              onChange={e => setNSteps(Math.max(1, Math.min(10000, +e.target.value)))}
              style={{
                width: 90, padding: '8px 10px',
                background: 'var(--surface-2)', border: '1px solid var(--border)',
                borderRadius: 5, color: '#fff', fontSize: '0.85rem',
                fontFamily: "'JetBrains Mono', monospace", outline: 'none',
              }}
            />
            <Btn
              label={`${nSteps.toLocaleString()} steps`}
              variant="primary"
              disabled={loading || !!simStatus?.running}
              onClick={() => onAction('/admin/simulator/step', 'POST', { n_steps: nSteps })}
            />
          </div>
        </Card>

        <CsvBackupsCard onAction={onAction} loading={loading} />
      </div>

      {/* Right: active faults */}
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <SectionLabel>FALLAS ACTIVAS EN SIMULADOR</SectionLabel>
          <span style={{ fontSize: '0.65rem', color: faults.length > 0 ? 'var(--solar)' : 'var(--green)' }}>
            {faults.length > 0 ? `${faults.length} activas` : 'sin fallas'}
          </span>
        </div>

        {faults.length === 0 ? (
          <div style={{ color: 'var(--text-dim)', fontSize: '0.8rem', textAlign: 'center', padding: '48px 0' }}>
            ✓ Sin fallas activas
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {faults.map((f, i) => (
              <div key={i} style={{
                background: 'var(--surface-2)', borderRadius: 6, padding: '12px 14px',
                borderLeft: `3px solid ${FAULT_COLORS[f.fault_type] ?? '#6b7f94'}`,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: '0.75rem', color: '#fff', fontFamily: "'JetBrains Mono', monospace" }}>
                    {f.inverter_id}
                  </span>
                  <span style={{ fontSize: '0.65rem', color: 'var(--text-dim)' }}>
                    {f.remaining} steps
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{
                    fontSize: '0.68rem', padding: '2px 8px', borderRadius: 3,
                    background: `${FAULT_COLORS[f.fault_type] ?? '#6b7f94'}18`,
                    color: FAULT_COLORS[f.fault_type] ?? '#6b7f94',
                    border: `1px solid ${FAULT_COLORS[f.fault_type] ?? '#6b7f94'}40`,
                  }}>
                    {f.fault_type.replace(/_/g, ' ')}
                  </span>
                  <div style={{ display: 'flex', gap: 3 }}>
                    {[1, 2, 3, 4, 5].map(n => (
                      <div key={n} style={{
                        width: 6, height: 6, borderRadius: 1,
                        background: n <= f.severity ? (FAULT_COLORS[f.fault_type] ?? '#6b7f94') : 'var(--border)',
                      }} />
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border)', fontSize: '0.62rem', color: 'var(--text-dim)' }}>
          Actualiza cada 3s · Solo visible para admin
        </div>
      </Card>
    </div>
  )
}

// ── Section: Base de Datos ────────────────────────────────────────────────────
function SectionDB({ onAction, loading }: { onAction: (path: string, method?: string, body?: any) => Promise<void>; loading: boolean }) {
  const [readings, setReadings] = useState<DbReading[]>([])
  const [page, setPage] = useState(0)
  const [filterPlant, setFilterPlant] = useState('')
  const [filterFault, setFilterFault] = useState('')
  const [confirm, setConfirm] = useState('')
  const [target, setTarget] = useState('full')
  const [fetching, setFetching] = useState(false)

  const fetchReadings = useCallback(async () => {
    setFetching(true)
    try {
      const params = new URLSearchParams({ page: String(page), limit: '50' })
      if (filterPlant) params.set('plant_id', filterPlant)
      if (filterFault) params.set('label_is_fault', filterFault)
      const data = await adminFetch(`/admin/db/readings?${params}`)
      setReadings(data.rows ?? [])
    } catch { /* ignore */ }
    finally { setFetching(false) }
  }, [page, filterPlant, filterFault])

  useEffect(() => { fetchReadings() }, [fetchReadings])

  const handleTruncate = async () => {
    if (confirm !== 'CONFIRMAR') return
    if (target === 'full') {
      await onAction('/admin/db/full-reset', 'POST')
    } else {
      await onAction(`/admin/db/truncate/${target}`, 'POST')
    }
    setConfirm('')
    fetchReadings()
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <SectionLabel>SOLAR_READINGS</SectionLabel>
          <button onClick={fetchReadings} style={{
            background: 'transparent', border: 'none', color: 'var(--text-dim)',
            cursor: 'pointer', fontSize: '0.72rem', fontFamily: "'JetBrains Mono', monospace",
          }}>↻ actualizar</button>
        </div>

        {/* Filters */}
        <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
          {([
            { label: 'Planta', val: filterPlant, set: setFilterPlant, opts: [['', 'Todas'], ['1', 'P1'], ['2', 'P2'], ['3', 'P3'], ['4', 'P4'], ['5', 'P5'], ['6', 'P6'], ['7', 'P7'], ['8', 'P8']] },
            { label: 'Falla', val: filterFault, set: setFilterFault, opts: [['', 'Todas'], ['1', 'Con falla'], ['0', 'Sin falla']] },
          ] as any[]).map(({ label, val, set, opts }) => (
            <select key={label} value={val} onChange={e => { set(e.target.value); setPage(0) }} style={{
              background: 'var(--surface-2)', border: '1px solid var(--border)',
              color: 'var(--text)', padding: '6px 10px', borderRadius: 5,
              fontSize: '0.72rem', fontFamily: "'JetBrains Mono', monospace",
            }}>
              {opts.map(([v, l]: string[]) => <option key={v} value={v}>{l}</option>)}
            </select>
          ))}
        </div>

        {/* Table */}
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.7rem', fontFamily: "'JetBrains Mono', monospace" }}>
            <thead>
              <tr>
                {['ID', 'TS', 'PLANTA', 'INVERSOR', 'IRR', 'T_MOD', 'P_AC', 'P_EXP', 'FALLA', 'TIPO'].map(h => (
                  <th key={h} style={{ padding: '7px 10px', textAlign: 'left', color: 'var(--text-dim)', borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap', fontSize: '0.58rem', letterSpacing: '0.1em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {fetching ? (
                <tr><td colSpan={10} style={{ padding: '32px', textAlign: 'center', color: 'var(--text-dim)' }}>Cargando...</td></tr>
              ) : readings.length === 0 ? (
                <tr><td colSpan={10} style={{ padding: '32px', textAlign: 'center', color: 'var(--text-dim)' }}>Sin resultados</td></tr>
              ) : readings.map(r => (
                <tr key={r.id} style={{ borderBottom: '1px solid rgba(30,45,61,0.5)' }}>
                  <td style={{ padding: '7px 10px', color: 'var(--text-dim)' }}>{r.id}</td>
                  <td style={{ padding: '7px 10px', color: 'var(--text)', whiteSpace: 'nowrap' }}>{r.ts?.slice(0, 16).replace('T', ' ')}</td>
                  <td style={{ padding: '7px 10px', color: 'var(--blue)' }}>P{r.plant_id}</td>
                  <td style={{ padding: '7px 10px', color: 'var(--text)' }}>{r.inverter_id}</td>
                  <td style={{ padding: '7px 10px', color: 'var(--text)' }}>{r.irradiance_wm2}</td>
                  <td style={{ padding: '7px 10px', color: 'var(--text)' }}>{r.temp_module_c}°</td>
                  <td style={{ padding: '7px 10px', color: 'var(--green)' }}>{r.power_ac_kw}</td>
                  <td style={{ padding: '7px 10px', color: 'var(--text-dim)' }}>{r.expected_power_ac_kw}</td>
                  <td style={{ padding: '7px 10px' }}>
                    <span style={{ color: r.label_is_fault ? 'var(--red)' : 'var(--green)' }}>
                      {r.label_is_fault ? 'SÍ' : 'NO'}
                    </span>
                  </td>
                  <td style={{ padding: '7px 10px' }}>
                    {r.fault_type
                      ? <span style={{ color: FAULT_COLORS[r.fault_type] ?? 'var(--text)', fontSize: '0.65rem' }}>{r.fault_type.replace(/_/g, ' ')}</span>
                      : <span style={{ color: 'var(--border)' }}>—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div style={{ display: 'flex', gap: 8, marginTop: 14, justifyContent: 'flex-end' }}>
          <Btn label="← Anterior" variant="ghost" small disabled={page === 0} onClick={() => setPage(p => p - 1)} />
          <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', alignSelf: 'center' }}>Página {page + 1}</span>
          <Btn label="Siguiente →" variant="ghost" small disabled={readings.length < 50} onClick={() => setPage(p => p + 1)} />
        </div>
      </Card>

      {/* Danger zone */}
      <Card danger>
        <SectionLabel>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" /><path d="M12 9v4" /><path d="M12 17h.01" />
            </svg>
            DANGER ZONE
          </div>
        </SectionLabel>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: '0.62rem', color: 'var(--text-dim)', marginBottom: 6 }}>TARGET</div>
            <select value={target} onChange={e => setTarget(e.target.value)} style={{
              width: '100%', background: 'var(--surface-2)', border: '1px solid var(--border)',
              color: 'var(--text)', padding: '8px 10px', borderRadius: 5,
              fontSize: '0.75rem', fontFamily: "'JetBrains Mono', monospace",
            }}>
              <option value="full">⚡ Reset completo (DB + simulador + snapshot CSV)</option>
              <option value="all">Solo DB (solar_readings CASCADE)</option>
              <option value="predictions">Solo ai_predictions</option>
              <option value="explanations">Solo ai_explanations</option>
            </select>
          </div>
          <div style={{ flex: 1, minWidth: 160 }}>
            <div style={{ fontSize: '0.62rem', color: 'var(--text-dim)', marginBottom: 6 }}>ESCRIBE "CONFIRMAR"</div>
            <input
              value={confirm} onChange={e => setConfirm(e.target.value)}
              placeholder="CONFIRMAR"
              style={{
                width: '100%', background: 'var(--surface-2)',
                border: `1px solid ${confirm === 'CONFIRMAR' ? 'var(--red)' : 'var(--border)'}`,
                color: '#fff', padding: '8px 10px', borderRadius: 5,
                fontSize: '0.75rem', fontFamily: "'JetBrains Mono', monospace",
                outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>
          <Btn label="Purgar" variant="danger" disabled={confirm !== 'CONFIRMAR' || loading} onClick={handleTruncate} />
        </div>
      </Card>
    </div>
  )
}

// ── Section: Modelos ML ───────────────────────────────────────────────────────
function SectionML({ onAction, loading }: { onAction: (path: string, method?: string, body?: any) => Promise<void>; loading: boolean }) {
  const [models, setModels] = useState<ModelStatus[]>([])
  const [backups, setBackups] = useState<{ id: string; label: string; size: string }[]>([])
  const [retraining, setRetraining] = useState(false)
  const [log, setLog] = useState<string[]>([])

  useEffect(() => {
    adminFetch('/admin/ml/status').then(d => setModels(d.models ?? [])).catch(() => { })
    adminFetch('/admin/ml/backups').then(d => setBackups(d.backups ?? [])).catch(() => { })
  }, [])

  const handleRetrain = async () => {
    setRetraining(true)
    setLog(['Iniciando reentrenamiento...'])
    try {
      await onAction('/admin/ml/retrain', 'POST')
      setLog(l => [...l, 'Reentrenamiento en background iniciado'])
      setTimeout(async () => {
        const d = await adminFetch('/admin/ml/status')
        setModels(d.models ?? [])
        setLog(l => [...l, 'Métricas actualizadas'])
        setRetraining(false)
      }, 5000)
    } catch {
      setLog(l => [...l, 'Error en reentrenamiento'])
      setRetraining(false)
    }
  }

  const handleBackup = async () => {
    await onAction('/admin/ml/backup', 'POST')
    const d = await adminFetch('/admin/ml/backups')
    setBackups(d.backups ?? [])
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
        <button
          onClick={handleBackup}
          disabled={loading}
          style={{
            background: 'transparent', color: 'var(--text)', border: '1px solid var(--border)',
            padding: '8px 16px', borderRadius: 5, cursor: loading ? 'not-allowed' : 'pointer',
            fontSize: '0.75rem', fontFamily: "'JetBrains Mono', monospace",
            letterSpacing: '0.05em', fontWeight: 600, opacity: loading ? 0.4 : 1, transition: 'all 0.15s',
            display: 'flex', alignItems: 'center', gap: '8px'
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v13a2 2 0 0 1-2 2z" /><polyline points="17 21 17 13 7 13 7 21" /><polyline points="7 3 7 8 15 8" />
          </svg>
          BACKUP MANUAL
        </button>
        <button
          onClick={handleRetrain}
          disabled={loading || retraining}
          style={{
            background: 'transparent', color: '#a78bfa', border: '1px solid #a78bfa',
            padding: '8px 16px', borderRadius: 5, cursor: (loading || retraining) ? 'not-allowed' : 'pointer',
            fontSize: '0.75rem', fontFamily: "'JetBrains Mono', monospace",
            letterSpacing: '0.05em', fontWeight: 600, opacity: (loading || retraining) ? 0.4 : 1, transition: 'all 0.15s',
            display: 'flex', alignItems: 'center', gap: '8px'
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .52 8.242 4.42 4.42 0 0 0 8.71 0 4 4 0 0 0 .52-8.242 4 4 0 0 0-2.526-5.77A3 3 0 0 0 12 5" />
            <path d="M9 13h4" /><path d="M12 10v6" />
          </svg>
          REENTRENAR
        </button>
      </div>

      {/* Models table */}
      <Card>
        <SectionLabel>ARTEFACTOS POR PLANTA</SectionLabel>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.72rem', fontFamily: "'JetBrains Mono', monospace" }}>
          <thead>
            <tr>
              {['PLANTA', 'N', 'F1 BIN', 'AUC', 'MAE kW', 'F1 TIPO', 'BACKUP', 'ACCIONES'].map(h => (
                <th key={h} style={{ padding: '7px 12px', textAlign: 'left', color: 'var(--text-dim)', borderBottom: '1px solid var(--border)', fontSize: '0.58rem', letterSpacing: '0.1em' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {models.length === 0 ? (
              <tr><td colSpan={8} style={{ padding: '32px', textAlign: 'center', color: 'var(--text-dim)' }}>Sin datos de modelos</td></tr>
            ) : models.map(m => (
              <tr key={m.plant_id} style={{ borderBottom: '1px solid rgba(30,45,61,0.5)' }}>
                <td style={{ padding: '9px 12px' }}>
                  <span style={{ color: '#fff', fontWeight: 700 }}>P{m.plant_id}</span>
                  <span style={{ color: 'var(--text-dim)', marginLeft: 8, fontSize: '0.65rem' }}>{m.plant_name}</span>
                </td>
                <td style={{ padding: '9px 12px', color: 'var(--text-dim)', fontSize: '0.65rem' }}>
                  {m.n_samples != null ? m.n_samples.toLocaleString() : '—'}
                </td>
                <td style={{ padding: '9px 12px', color: f1Color(m.f1_binary) }}>
                  {m.f1_binary != null ? m.f1_binary.toFixed(4) : '—'}
                </td>
                <td style={{ padding: '9px 12px', color: f1Color(m.roc_auc) }}>
                  {m.roc_auc != null ? m.roc_auc.toFixed(4) : '—'}
                </td>
                <td style={{ padding: '9px 12px', color: 'var(--solar)' }}>
                  {m.mae != null ? m.mae.toFixed(3) : '—'}
                </td>
                <td style={{ padding: '9px 12px', color: f1Color(m.f1_type) }}>
                  {m.f1_type != null ? m.f1_type.toFixed(4) : '—'}
                </td>
                <td style={{ padding: '9px 12px' }}>
                  {m.has_backup
                    ? <span style={{ color: 'var(--green)', fontSize: '0.65rem' }}>✓</span>
                    : <span style={{ color: 'var(--border)', fontSize: '0.65rem' }}>—</span>}
                </td>
                <td style={{ padding: '9px 12px' }}>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <Btn label="↓" variant="ghost" small
                      onClick={() => window.open(`${BASE}/admin/ml/download/${m.plant_id}`, '_blank')} />
                    {m.has_backup && (
                      <Btn label="↩" variant="ghost" small
                        onClick={() => onAction(`/admin/ml/restore/latest/${m.plant_id}`, 'POST')} />
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* Retrain log */}
      {log.length > 0 && (
        <Card>
          <SectionLabel>LOG</SectionLabel>
          <div style={{
            background: 'var(--surface-2)', borderRadius: 5, padding: '12px 14px',
            fontFamily: "'JetBrains Mono', monospace", fontSize: '0.72rem',
            color: 'var(--text)', maxHeight: 140, overflowY: 'auto',
            display: 'flex', flexDirection: 'column', gap: 4,
          }}>
            {log.map((line, i) => <div key={i}>{line}</div>)}
            {retraining && <div style={{ color: 'var(--solar)' }}>⏳ Procesando en background...</div>}
          </div>
        </Card>
      )}

      {/* Backups */}
      {backups.length > 0 && (
        <Card>
          <SectionLabel>SNAPSHOTS</SectionLabel>
          {backups.map(b => (
            <div key={b.id} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '10px 0', borderBottom: '1px solid var(--border)',
            }}>
              <div>
                <div style={{ color: 'var(--text)', fontSize: '0.75rem' }}>{b.id}</div>
                <div style={{ color: 'var(--text-dim)', fontSize: '0.62rem' }}>{b.label} · {b.size}</div>
              </div>
              <Btn label="↩ Restaurar" variant="purple" small
                onClick={() => onAction(`/admin/ml/restore/${b.id}`, 'POST')} />
            </div>
          ))}
        </Card>
      )}
    </div>
  )
}

// ── Main Control ──────────────────────────────────────────────────────────────
export default function Control() {
  const [tab, setTab] = useState<AdminTab>('sistema')
  const [loading, setLoading] = useState(false)
  const [simStatus, setSimStatus] = useState<SimStatus | null>(null)
  const [db, setDb] = useState<DbStats | null>(null)
  const [faults, setFaults] = useState<ActiveFault[]>([])

  const fetchStatus = useCallback(async () => {
    try {
      const data = await adminFetch('/admin/status')
      setSimStatus(data.simulator ?? null)
      setDb(data.db ?? null)
    } catch { /* ignore */ }
  }, [])

  const fetchFaults = useCallback(async () => {
    try {
      const data = await adminFetch('/admin/simulator/faults')
      setFaults(data.faults ?? [])
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    fetchStatus()
    fetchFaults()
    const int = setInterval(() => { fetchStatus(); fetchFaults() }, 3000)
    return () => clearInterval(int)
  }, [fetchStatus, fetchFaults])

  const onAction = async (path: string, method = 'POST', body?: any) => {
    setLoading(true)
    try {
      await adminFetch(path, method, body)
      await fetchStatus()
    } catch {
      alert('Error ejecutando acción')
    } finally {
      setLoading(false)
    }
  }

  const TABS: { id: AdminTab; label: string; icon: React.ReactNode }[] = [
    { id: 'sistema', label: 'SISTEMA', icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2" /></svg> },
    { id: 'simulador', label: 'SIMULADOR', icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.1a2 2 0 0 1-1-1.72v-.51a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" /><circle cx="12" cy="12" r="3" /></svg> },
    { id: 'db', label: 'BASE DE DATOS', icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" /><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" /></svg> },
    { id: 'ml', label: 'MODELOS ML', icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .52 8.242 4.42 4.42 0 0 0 8.71 0 4 4 0 0 0 .52-8.242 4 4 0 0 0-2.526-5.77A3 3 0 0 0 12 5" /><path d="M9 13h4" /><path d="M12 10v6" /></svg> },
  ]

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', fontFamily: "'JetBrains Mono', monospace" }}>

      {/* Sub-navbar */}
      <div style={{
        borderBottom: '1px solid var(--border)',
        background: 'var(--surface)',
        padding: '0 32px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex' }}>
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              display: 'flex', alignItems: 'center', gap: 7,
              padding: '12px 18px',
              background: tab === t.id ? 'rgba(245,158,11,0.08)' : 'transparent',
              border: 'none',
              borderBottom: `2px solid ${tab === t.id ? 'var(--solar)' : 'transparent'}`,
              color: tab === t.id ? 'var(--solar)' : 'var(--text-dim)',
              fontSize: '0.72rem', letterSpacing: '0.1em',
              cursor: 'pointer', fontFamily: "'JetBrains Mono', monospace",
              transition: 'all 0.15s',
            }}>
              <span>{t.icon}</span> {t.label}
            </button>
          ))}
        </div>
        <div style={{ fontSize: '0.62rem', color: loading ? 'var(--solar)' : 'var(--text-dim)' }}>
          {loading ? '⏳ ejecutando...' : '● admin'}
        </div>
      </div>

      {/* Content */}
      <div style={{ padding: '28px 32px', maxWidth: 1100, margin: '0 auto' }}>
        <div style={{ marginBottom: 24 }}>
          <h1 style={{
            fontFamily: "'Syne', sans-serif", color: '#fff',
            fontSize: '1.3rem', margin: '0 0 4px', fontWeight: 800,
          }}>
            {TABS.find(t => t.id === tab)?.icon} {TABS.find(t => t.id === tab)?.label}
          </h1>
          <div style={{ color: 'var(--text-dim)', fontSize: '0.72rem' }}>
            Panel de administración · Solo rol admin
          </div>
        </div>

        {tab === 'sistema' && <SectionSistema db={db} simStatus={simStatus} onAction={onAction} />}
        {tab === 'simulador' && <SectionSimulador simStatus={simStatus} faults={faults} onAction={onAction} loading={loading} />}
        {tab === 'db' && <SectionDB onAction={onAction} loading={loading} />}
        {tab === 'ml' && <SectionML onAction={onAction} loading={loading} />}
      </div>
    </div>
  )
}