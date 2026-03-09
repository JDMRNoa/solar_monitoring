import { useState, useEffect } from 'react'

interface SimStatus {
  running: boolean
  step_count: number
  total_records: number
  total_faults: number
  fault_rate_pct: number
  last_ts: string | null
}

export default function Control() {
  const [status, setStatus] = useState<SimStatus | null>(null)
  const [dbStatus, setDbStatus] = useState({ readings: 0, predictions: 0 })
  const [loading, setLoading] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [truncateTarget, setTruncateTarget] = useState<'readings'|'predictions'|'all'>('all')

  const baseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api'
  const token = (typeof document !== 'undefined') ? 
    document.cookie.split('; ').find(row => row.startsWith('solarmonitor_jwt='))?.split('=')[1] 
    : ''

  const fetchStatus = async () => {
    try {
      const res = await fetch(`${baseUrl}/admin/status`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        setStatus(data.simulator)
        setDbStatus({ readings: data.db.solar_readings, predictions: data.db.ai_predictions })
      }
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    fetchStatus()
    const int = setInterval(fetchStatus, 3000)
    return () => clearInterval(int)
  }, [])

  const handleAction = async (endpoint: string, method = 'POST', body?: any) => {
    setLoading(true)
    try {
      await fetch(`${baseUrl}/admin/${endpoint}`, {
        method,
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: body ? JSON.stringify(body) : undefined
      })
      await fetchStatus()
    } catch (e) {
      alert("Error ejecutando acción")
    } finally {
      setLoading(false)
    }
  }

  const handleTruncate = async () => {
    if (confirmText !== 'CONFIRMAR') {
      alert('Escribe CONFIRMAR para proceder.')
      return
    }
    await handleAction(`db/truncate/${truncateTarget}`, 'POST')
    setConfirmText('')
  }

  return (
    <div style={{ maxWidth: '900px', margin: '0 auto', padding: '40px 20px', fontFamily: 'Inter, sans-serif' }}>
      
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
        <div>
          <h1 style={{ fontFamily: 'Syne, sans-serif', color: '#fff', margin: '0 0 8px', fontSize: '1.8rem' }}>Panel de Control (Admin)</h1>
          <p style={{ color: 'var(--text-dim)', margin: 0, fontSize: '0.9rem' }}>Gestiona el Simulador Solar, la Base de Datos y el pipeline de ML.</p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px', marginBottom: '24px' }}>
        
        {/* Simulator Card */}
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '8px', padding: '24px' }}>
          <h2 style={{ color: '#fff', fontSize: '1.1rem', margin: '0 0 16px', fontFamily: 'Syne, sans-serif' }}>⚙️ Simulador Físico</h2>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' }}>
            <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: status?.running ? '#3fb950' : '#f85149' }} />
            <span style={{ color: 'var(--text-dim)', fontSize: '0.9rem' }}>
              Estado: <strong style={{ color: '#fff' }}>{status?.running ? 'Corriendo' : 'Detenido'}</strong>
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '20px' }}>
            <div style={{ background: 'rgba(0,0,0,0.2)', padding: '10px', borderRadius: '4px' }}>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-dim)', letterSpacing: '0.05em' }}>REGISTROS TOTALES</div>
              <div style={{ fontSize: '1.2rem', color: '#fff', fontFamily: 'JetBrains Mono, monospace' }}>{status?.total_records || 0}</div>
            </div>
            <div style={{ background: 'rgba(0,0,0,0.2)', padding: '10px', borderRadius: '4px' }}>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-dim)', letterSpacing: '0.05em' }}>TASA DE FALLAS</div>
              <div style={{ fontSize: '1.2rem', color: '#f59e0b', fontFamily: 'JetBrains Mono, monospace' }}>{status?.fault_rate_pct || 0}%</div>
            </div>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
            {!status?.running ? (
              <button 
                onClick={() => handleAction('simulator/start')}
                disabled={loading}
                style={{ background: '#3fb950', color: '#000', border: 'none', padding: '8px 16px', borderRadius: '4px', cursor: 'pointer', fontWeight: 600, fontSize: '0.8rem' }}>
                ▶ Iniciar
              </button>
            ) : (
              <button 
                onClick={() => handleAction('simulator/stop')}
                disabled={loading}
                style={{ background: '#f85149', color: '#fff', border: 'none', padding: '8px 16px', borderRadius: '4px', cursor: 'pointer', fontWeight: 600, fontSize: '0.8rem' }}>
                ⏸ Detener
              </button>
            )}
            <button 
              onClick={() => handleAction('simulator/step?n_steps=1')}
              disabled={loading || status?.running}
              style={{ background: 'var(--surface)', color: '#fff', border: '1px solid var(--border)', padding: '8px 16px', borderRadius: '4px', cursor: (loading || status?.running) ? 'not-allowed' : 'pointer', fontSize: '0.8rem' }}>
              +1 Paso
            </button>
            <button 
              onClick={() => handleAction('simulator/reset', 'DELETE')}
              disabled={loading || status?.running}
              style={{ background: 'transparent', color: 'var(--text-dim)', border: '1px solid var(--border)', padding: '8px 16px', borderRadius: '4px', cursor: (loading || status?.running) ? 'not-allowed' : 'pointer', fontSize: '0.8rem', marginLeft: 'auto' }}>
              ↺ Hard Reset
            </button>
          </div>
        </div>

        {/* Database & ML Card */}
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '8px', padding: '24px' }}>
          <h2 style={{ color: '#fff', fontSize: '1.1rem', margin: '0 0 16px', fontFamily: 'Syne, sans-serif' }}>🗄️ Base de Datos y Modelos</h2>
          
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '24px' }}>
            <div style={{ background: 'rgba(0,0,0,0.2)', padding: '10px', borderRadius: '4px', borderLeft: '2px solid #58a6ff' }}>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-dim)', letterSpacing: '0.05em' }}>TABLA READINGS</div>
              <div style={{ fontSize: '1.1rem', color: '#fff', fontFamily: 'JetBrains Mono, monospace' }}>{dbStatus.readings} records</div>
            </div>
            <div style={{ background: 'rgba(0,0,0,0.2)', padding: '10px', borderRadius: '4px', borderLeft: '2px solid #a78bfa' }}>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-dim)', letterSpacing: '0.05em' }}>TABLA PREDICTIONS</div>
              <div style={{ fontSize: '1.1rem', color: '#fff', fontFamily: 'JetBrains Mono, monospace' }}>{dbStatus.predictions} records</div>
            </div>
          </div>

          <h3 style={{ color: '#f85149', fontSize: '0.85rem', margin: '0 0 12px', letterSpacing: '0.05em' }}>DANGER ZONE (TRUNCATE)</h3>
          <div style={{ background: 'rgba(248, 81, 73, 0.05)', border: '1px solid rgba(248, 81, 73, 0.3)', padding: '16px', borderRadius: '6px' }}>
            <select 
              value={truncateTarget} 
              onChange={(e: any) => setTruncateTarget(e.target.value)}
              style={{ width: '100%', marginBottom: '12px', background: 'var(--surface)', color: '#fff', border: '1px solid var(--border)', padding: '8px', borderRadius: '4px' }}
            >
              <option value="all">Limpiar Ambas Tablas (ALL)</option>
              <option value="readings">Solo Leerings (solar_readings)</option>
              <option value="predictions">Solo Predicciones (ai_predictions)</option>
            </select>

            <div style={{ display: 'flex', gap: '8px' }}>
              <input 
                type="text" 
                placeholder="Escribe CONFIRMAR" 
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                style={{ flex: 1, background: 'var(--surface)', color: '#fff', border: '1px solid var(--border)', padding: '8px 12px', borderRadius: '4px', outline: 'none' }}
              />
              <button 
                onClick={handleTruncate}
                disabled={loading || confirmText !== 'CONFIRMAR'}
                style={{ background: confirmText === 'CONFIRMAR' ? '#f85149' : 'var(--surface)', color: confirmText === 'CONFIRMAR' ? '#fff' : 'var(--text-dim)', border: 'none', padding: '8px 16px', borderRadius: '4px', cursor: confirmText === 'CONFIRMAR' ? 'pointer' : 'not-allowed', fontWeight: 600, fontSize: '0.8rem' }}>
                Purgar
              </button>
            </div>
          </div>

           <div style={{ marginTop: '24px', paddingTop: '16px', borderTop: '1px solid var(--border)' }}>
             <button 
                onClick={() => handleAction('ml/retrain')}
                disabled={loading}
                style={{ width: '100%', background: 'transparent', color: '#a78bfa', border: '1px solid #a78bfa', padding: '10px', borderRadius: '4px', cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem', transition: 'all 0.2s' }}>
                🧠 Forzar Reentrenamiento ML
              </button>
           </div>
        </div>
      </div>
    </div>
  )
}
