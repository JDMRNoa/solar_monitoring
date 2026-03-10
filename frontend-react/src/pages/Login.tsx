import { useState } from 'react'

interface LoginProps {
  onLoginSuccess: (token: string, role: string) => void
}

export default function Login({ onLoginSuccess }: LoginProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [focused, setFocused]   = useState<number | null>(null)

  const handleSubmit = async () => {
    setError('')
    setLoading(true)
    try {
      const baseUrl  = import.meta.env.VITE_API_BASE_URL ?? '/api'
      const response = await fetch(`${baseUrl}/auth/login`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ username, password }),
      })
      if (!response.ok) throw new Error('Credenciales incorrectas')
      const data = await response.json()
      onLoginSuccess(data.access_token, data.role)
    } catch (err: any) {
      setError(err.message || 'Error de conexión')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      background: '#0a0a0a',
      fontFamily: "'JetBrains Mono', monospace",
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Grid background */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: `
          linear-gradient(rgba(245,158,11,0.04) 1px, transparent 1px),
          linear-gradient(90deg, rgba(245,158,11,0.04) 1px, transparent 1px)
        `,
        backgroundSize: '40px 40px',
        pointerEvents: 'none',
      }} />

      {/* ── Left panel — branding ───────────────────────────────────── */}
      <div style={{
        width: '55%',
        padding: '60px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        position: 'relative',
        zIndex: 1,
      }}>
        <div>
          {/* Status dot */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10,
            marginBottom: 80,
          }}>
            <div style={{
              width: 8, height: 8, borderRadius: '50%',
              background: 'var(--solar)',
              boxShadow: '0 0 12px var(--solar)',
            }} />
            <span style={{
              color: 'var(--solar)',
              fontSize: '0.65rem',
              letterSpacing: '0.2em',
            }}>
              SOLAR MONITOR v2.1
            </span>
          </div>

          {/* Hero text */}
          <h1 style={{
            fontFamily: "'Syne', sans-serif",
            fontSize: 'clamp(2rem, 4vw, 3.8rem)',
            color: '#fff',
            lineHeight: 0.9,
            margin: '0 0 24px',
            letterSpacing: '0.02em',
            fontWeight: 800,
          }}>
            SOLAR<br />
            <span style={{ color: 'var(--solar)' }}>MONITOR</span><br />
            SYSTEM
          </h1>

          <p style={{
            color: '#555',
            fontSize: '0.75rem',
            lineHeight: 2,
            maxWidth: 360,
            letterSpacing: '0.03em',
          }}>
            Monitoreo en tiempo real · Detección de fallas ML<br />
            8 plantas fotovoltaicas · Colombia
          </p>
        </div>

        {/* Stats */}
        <div style={{ display: 'flex', gap: 40 }}>
          {[
            ['8',     'PLANTAS'],
            ['107K',  'LECTURAS'],
            ['99.7%', 'PRECISIÓN'],
          ].map(([val, label]) => (
            <div key={label}>
              <div style={{
                color: 'var(--solar)',
                fontSize: '1.4rem',
                fontWeight: 700,
              }}>{val}</div>
              <div style={{
                color: '#444',
                fontSize: '0.6rem',
                letterSpacing: '0.15em',
              }}>{label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Right panel — form ──────────────────────────────────────── */}
      <div style={{
        width: '45%',
        background: '#111',
        borderLeft: '1px solid #1e2d3d',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '60px 50px',
        position: 'relative',
        zIndex: 1,
      }}>
        <div style={{ width: '100%', maxWidth: 340 }}>

          {/* Divider label */}
          <div style={{
            fontSize: '0.6rem',
            color: '#444',
            letterSpacing: '0.2em',
            marginBottom: 40,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}>
            <div style={{ height: 1, flex: 1, background: '#1e2d3d' }} />
            AUTENTICACIÓN
            <div style={{ height: 1, flex: 1, background: '#1e2d3d' }} />
          </div>

          {/* Fields */}
          {[
            { label: 'USUARIO',     type: 'text',     value: username, setter: setUsername, idx: 0 },
            { label: 'CONTRASEÑA',  type: 'password', value: password, setter: setPassword, idx: 1 },
          ].map(({ label, type, value, setter, idx }) => (
            <div key={label} style={{ marginBottom: 28 }}>
              <div style={{
                fontSize: '0.6rem',
                color: focused === idx ? 'var(--solar)' : '#444',
                letterSpacing: '0.2em',
                marginBottom: 10,
                transition: 'color 0.2s',
              }}>{label}</div>
              <input
                type={type}
                value={value}
                onChange={e => setter(e.target.value)}
                onFocus={() => setFocused(idx)}
                onBlur={() => setFocused(null)}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                required
                style={{
                  width: '100%',
                  padding: '12px 0',
                  background: 'transparent',
                  border: 'none',
                  borderBottom: `1px solid ${focused === idx ? 'var(--solar)' : '#1e2d3d'}`,
                  color: '#fff',
                  fontSize: '0.9rem',
                  outline: 'none',
                  boxSizing: 'border-box',
                  transition: 'border-color 0.2s',
                  fontFamily: "'JetBrains Mono', monospace",
                }}
              />
            </div>
          ))}

          {/* Error */}
          {error && (
            <div style={{
              background: 'rgba(248,81,73,0.08)',
              border: '1px solid rgba(248,81,73,0.3)',
              color: '#f85149',
              padding: '10px 14px',
              fontSize: '0.72rem',
              letterSpacing: '0.03em',
              marginBottom: 20,
            }}>
              ✕ {error}
            </div>
          )}

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={loading}
            style={{
              width: '100%',
              marginTop: 12,
              padding: '14px',
              background: 'transparent',
              border: `1px solid ${loading ? '#333' : 'var(--solar)'}`,
              color: loading ? '#444' : 'var(--solar)',
              fontSize: '0.72rem',
              letterSpacing: '0.2em',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontFamily: "'JetBrains Mono', monospace",
              transition: 'all 0.2s',
            }}
            onMouseEnter={e => {
              if (!loading) {
                ;(e.target as HTMLButtonElement).style.background = 'var(--solar)'
                ;(e.target as HTMLButtonElement).style.color = '#000'
              }
            }}
            onMouseLeave={e => {
              ;(e.target as HTMLButtonElement).style.background = 'transparent'
              ;(e.target as HTMLButtonElement).style.color = loading ? '#444' : 'var(--solar)'
            }}
          >
            {loading ? 'VERIFICANDO...' : '→ INICIAR SESIÓN'}
          </button>

          {/* Hint */}
          <div style={{
            marginTop: 32,
            paddingTop: 24,
            borderTop: '1px solid #1a1a1a',
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
          }}>
            {[
              ['admin',    'Administrador'],
              ['operador', 'Solo lectura'],
            ].map(([u, r]) => (
              <div key={u} style={{ fontSize: '0.65rem', color: '#333' }}>
                <span style={{ color: '#555' }}>{u}</span>
                <span style={{ color: '#2a2a2a' }}> — {r}</span>
              </div>
            ))}
          </div>

        </div>
      </div>
    </div>
  )
}