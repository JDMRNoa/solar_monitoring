import { useRef, useEffect, useState, useCallback } from 'react'
import { useLiveWeather, type LivePlantData } from '../hooks/useLiveWeather'
import { fetchFaultEvents } from '../lib/api'
import type { FaultEvent } from '../types'

// ── Constantes ────────────────────────────────────────────────────────────────

const PLANT_META = [
  { id: 1, name: 'Caribe',        location: 'Barranquilla', capacity_kw: 200, panel_count: 500, inverter_count: 6 },
  { id: 2, name: 'Andina',        location: 'Bogotá',       capacity_kw: 80,  panel_count: 200, inverter_count: 3 },
  { id: 3, name: 'Paisa',         location: 'Medellín',     capacity_kw: 150, panel_count: 380, inverter_count: 5 },
  { id: 4, name: 'Valle',         location: 'Cali',         capacity_kw: 120, panel_count: 300, inverter_count: 4 },
  { id: 5, name: 'Llanos',        location: 'Villavicencio',capacity_kw: 90,  panel_count: 225, inverter_count: 3 },
  { id: 6, name: 'Guajira',       location: 'Riohacha',     capacity_kw: 300, panel_count: 750, inverter_count: 8 },
  { id: 7, name: 'Sierra Nevada', location: 'Santa Marta',  capacity_kw: 60,  panel_count: 150, inverter_count: 2 },
  { id: 8, name: 'Boyacá',        location: 'Tunja',        capacity_kw: 45,  panel_count: 112, inverter_count: 2 },
]

const FAULT_INFO: Record<string, { label: string; icon: string; color: string; bg: string }> = {
  inverter_derate: { label: 'Inverter Derate',  icon: '⚡', color: '#ff5722', bg: 'rgba(255,87,34,0.12)'  },
  sensor_flatline: { label: 'Sensor Flatline',  icon: '📡', color: '#9c27b0', bg: 'rgba(156,39,176,0.12)' },
  string_fault:    { label: 'String Fault',     icon: '🔌', color: '#f44336', bg: 'rgba(244,67,54,0.12)'  },
  grid_disconnect: { label: 'Grid Disconnect',  icon: '🔋', color: '#e91e63', bg: 'rgba(233,30,99,0.12)'  },
  mppt_failure:    { label: 'MPPT Failure',     icon: '📉', color: '#ff9800', bg: 'rgba(255,152,0,0.12)'  },
  partial_shading: { label: 'Partial Shading',  icon: '🌥', color: '#607d8b', bg: 'rgba(96,125,139,0.12)' },
  panel_soiling:   { label: 'Panel Soiling',    icon: '🟫', color: '#ffd600', bg: 'rgba(255,214,0,0.12)'  },
  pid_effect:      { label: 'PID Effect',       icon: '📶', color: '#ff6f00', bg: 'rgba(255,111,0,0.12)'  },
}

// ── Sparkline ─────────────────────────────────────────────────────────────────

function Sparkline({ history, maxKw }: { history: number[]; maxKw: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const c = ref.current
    if (!c || history.length < 2) return
    const ctx = c.getContext('2d')!
    const w = c.offsetWidth || 200; const h = c.offsetHeight || 44
    c.width = w; c.height = h
    ctx.clearRect(0, 0, w, h)
    const pts = history.slice(-48)
    const max = Math.max(...pts, maxKw * 0.01)
    const dx = w / (pts.length - 1)
    const grad = ctx.createLinearGradient(0, 0, 0, h)
    grad.addColorStop(0, 'rgba(0,212,255,0.28)')
    grad.addColorStop(1, 'rgba(0,212,255,0.0)')
    ctx.beginPath()
    pts.forEach((v, i) => {
      const x = i * dx; const y = h - (v / max) * (h * 0.82) - 3
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.strokeStyle = '#00d4ff'; ctx.lineWidth = 1.5; ctx.stroke()
    ctx.lineTo((pts.length - 1) * dx, h); ctx.lineTo(0, h); ctx.closePath()
    ctx.fillStyle = grad; ctx.fill()
  }, [history, maxKw])
  return <canvas ref={ref} style={{ width: '100%', height: '100%', display: 'block' }} />
}

// ── Panel Cells ───────────────────────────────────────────────────────────────

function PanelArray({ reading, meta }: { reading: LivePlantData | null; meta: typeof PLANT_META[0] }) {
  const pAc = reading?.power_ac_kw ?? 0
  const irr = reading?.irradiance_wm2 ?? 0
  const isNight = irr < 10
  // Efectos visuales del array basados en tipo ML inferido
  const ft = (reading?.fault_pred === 1 ? (reading as any).fault_type_pred : null) ?? ''
  const loadRatio = Math.min(1, pAc / meta.capacity_kw)
  const soiling = reading?.soiling ?? 0

  const getCellStyle = (i: number): React.CSSProperties => {
    if (!reading || isNight) return { background: '#0d1117' }
    if (ft === 'grid_disconnect' && (reading.fault_proba ?? 0) > 0.7)
      return { background: '#3a1a1a', boxShadow: '0 0 3px rgba(255,68,68,0.4)' }
    if (ft === 'partial_shading')
      return i < 12
        ? { background: '#0a0f15', opacity: 0.4 }
        : loadRatio > 0.6
          ? { background: 'linear-gradient(135deg,#1565c0,#0d47a1)', boxShadow: '0 0 4px rgba(21,101,192,0.5)' }
          : { background: 'linear-gradient(135deg,#1a4a7a,#0d3060)' }
    if (ft === 'string_fault')
      return i < 8
        ? { background: '#3a1a1a', boxShadow: '0 0 3px rgba(255,68,68,0.4)' }
        : { background: 'linear-gradient(135deg,#1a4a7a,#0d3060)' }
    if (loadRatio > 0.65)
      return { background: 'linear-gradient(135deg,#1565c0,#0d47a1)', boxShadow: '0 0 4px rgba(21,101,192,0.5)' }
    if (loadRatio > 0.15) return { background: 'linear-gradient(135deg,#1a4a7a,#0d3060)' }
    if (irr > 0)           return { background: '#1a3a5c' }
    return { background: '#0d1117' }
  }

  return (
    <div style={{
      display: 'grid', gridTemplateColumns: 'repeat(8,1fr)', gap: '2px',
      padding: '8px', background: '#080c10', borderRadius: '4px',
      border: '1px solid var(--border)', position: 'relative',
    }}>
      {Array.from({ length: 32 }).map((_, i) => (
        <div key={i} style={{
          aspectRatio: '1.4/1', borderRadius: '2px',
          transition: 'background 0.5s, opacity 0.5s',
          ...getCellStyle(i),
        }} />
      ))}
      {soiling > 0.05 && (
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none', borderRadius: '3px',
          background: `rgba(100,60,10,${Math.min(soiling * 0.55, 0.5)})`,
          transition: 'background 1s',
        }} />
      )}
    </div>
  )
}

// ── Inverter Row ──────────────────────────────────────────────────────────────

function InverterRow({ reading, meta }: { reading: LivePlantData | null; meta: typeof PLANT_META[0] }) {
  const loadPerInv = meta.capacity_kw / meta.inverter_count
  const visibleCount = Math.min(meta.inverter_count, 6)

  // Use real inverters array if available, or simulate fallback during loading
  const inverters = reading?.inverters ?? Array.from({ length: meta.inverter_count }).map((_, i) => ({
    inverter_id: `I${i+1}`,
    power_ac_kw: 0,
    fault_proba: 0,
    fault_pred: 0,
  } as LivePlantData))

  return (
    <div style={{ display: 'flex', gap: '4px', padding: '0 12px 10px' }}>
      {inverters.slice(0, visibleCount).map((inv, i) => {
        let invPow = inv.power_ac_kw ?? 0
        const ft = inv.fault_pred === 1 ? inv.fault_type_pred : null
        
        let border = 'rgba(0,230,118,0.3)', bg = 'transparent', color = 'var(--text)'
        
        if (ft === 'inverter_derate') {
          border = '#ffd600'; bg = 'rgba(255,214,0,0.08)'; color = '#ffd600'
        } else if (ft === 'grid_disconnect') {
          border = '#f44336'; bg = 'rgba(244,67,54,0.08)'; color = '#f44336'; invPow = 0
        } else if ((inv.fault_proba ?? 0) > 0.8) {
          border = '#f44336'; bg = 'rgba(244,67,54,0.08)'; color = '#f44336'
        }

        const pct = reading ? (loadPerInv > 0 ? Math.round((invPow / loadPerInv) * 100) : 0) : '–'
        const label = inv.inverter_id ? inv.inverter_id.substring(inv.inverter_id.length - 2).replace('-', '') : `I${i+1}`

        return (
          <div key={i} style={{
            flex: 1, background: bg || '#0a0e14',
            border: `1px solid ${border}`, borderRadius: '3px',
            padding: '4px 5px', textAlign: 'center', fontSize: '0.55rem', transition: 'all 0.4s',
          }}>
            <div style={{ color: 'var(--text-dim)', fontSize: '0.5rem', textTransform: 'uppercase' }}>{label}</div>
            <div style={{ fontSize: '0.72rem', fontWeight: 700, color }}>{pct !== '–' ? `${pct}%` : '–'}</div>
          </div>
        )
      })}
      {meta.inverter_count > visibleCount && (
        <div style={{ display: 'flex', alignItems: 'center', fontSize: '0.52rem', color: 'var(--text-dim)', paddingLeft: '2px' }}>
          +{meta.inverter_count - visibleCount}
        </div>
      )}
    </div>
  )
}

// ── Weather Bar (por planta seleccionada) ─────────────────────────────────────

function WeatherBar({
  data,
  selectedId,
  onSelect,
}: {
  data: Record<number, LivePlantData>
  selectedId: number
  onSelect: (id: number) => void
}) {
  const r = data[selectedId] ?? Object.values(data)[0]
  const meta = PLANT_META.find(m => m.id === selectedId) ?? PLANT_META[0]

  if (!r) return (
    <div style={{ fontSize: '0.65rem', color: 'var(--text-dim)', fontStyle: 'italic', marginBottom: '20px', borderBottom: '1px solid var(--border)', paddingBottom: '12px' }}>
      Sin datos de clima en tiempo real — arranca el simulador.
    </div>
  )

  const cloudPct   = r.cloud_cover != null ? Math.round(r.cloud_cover * 100) : null
  const soilingPct = r.soiling != null ? Math.round(r.soiling * 100) : null

  return (
    <div style={{
      borderBottom: '1px solid var(--border)', marginBottom: '20px', paddingBottom: '12px',
    }}>
      {/* Datos de clima — planta seleccionada desde las tarjetas */}
      <div style={{
        display: 'flex', gap: '20px', flexWrap: 'wrap', alignItems: 'center',
        fontSize: '0.68rem', color: 'var(--text-dim)',
      }}>
        <span style={{ textTransform: 'uppercase', letterSpacing: '0.1em', fontSize: '0.60rem', flexShrink: 0, color: '#f59e0b' }}>
          {meta.name}
        </span>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span>☁</span>
          <span>Nubosidad:</span>
          <div style={{ width: '50px', height: '4px', background: 'var(--border)', borderRadius: '2px', overflow: 'hidden' }}>
            <div style={{ height: '100%', borderRadius: '2px', transition: 'width 1s', background: 'linear-gradient(90deg,#4fc3f7,#81d4fa)', width: cloudPct != null ? cloudPct + '%' : '0%' }} />
          </div>
          <span>{cloudPct != null ? cloudPct + '%' : '–'}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span>🌡</span>
          <span>{r.temp_ambient_c != null ? r.temp_ambient_c.toFixed(1) + '°C' : '–'}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span>💨</span>
          <span>{r.wind_ms != null ? r.wind_ms.toFixed(1) + ' m/s' : '–'}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span>☀</span>
          <span>{r.irradiance_wm2 != null ? Math.round(r.irradiance_wm2) + ' W/m²' : '–'}</span>
        </div>

        {soilingPct != null && soilingPct > 5 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span>🟫</span>
            <span style={{ color: soilingPct > 15 ? '#ffd600' : 'var(--text-dim)' }}>
              Suciedad: {soilingPct}%
            </span>
          </div>
        )}

        {r.rain_active && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span>🌧</span>
            <span style={{ color: '#00d4ff' }}>Lluvia – limpieza paneles</span>
          </div>
        )}
      </div>
    </div>
  )
}

// ── ML Badge ──────────────────────────────────────────────────────────────────

function MlBadge({ reading }: { reading: LivePlantData | null }) {
  if (!reading?.fault_proba) return null
  const pct = Math.round(reading.fault_proba * 100)
  const color = pct > 80 ? '#f85149' : pct > 50 ? '#f59e0b' : '#3fb950'
  return (
    <div style={{
      padding: '4px 10px', borderTop: '1px solid var(--border)',
      display: 'flex', gap: '12px', fontSize: '0.6rem', color: 'var(--text-dim)',
    }}>
      <span>ML · Prob: <span style={{ color, fontWeight: 700 }}>{pct}%</span></span>
      {reading.power_residual_kw != null && (
        <span>Δ <span style={{ color: Math.abs(reading.power_residual_kw) > 5 ? '#f59e0b' : 'var(--text)' }}>
          {reading.power_residual_kw.toFixed(1)} kW
        </span></span>
      )}
    </div>
  )
}

// ── Plant Card ────────────────────────────────────────────────────────────────

function PlantCard({ meta, reading, history, loading, onDashboard, onWeatherSelect, isWeatherActive }: {
  meta: typeof PLANT_META[0]
  reading: LivePlantData | null
  history: number[]
  loading: boolean
  onDashboard: () => void
  onWeatherSelect: () => void
  isWeatherActive: boolean
}) {
  // Estado visual basado en ML (fault_proba) — no en ground truth del simulador
  const mlProba    = reading?.fault_proba ?? 0
  const mlFault    = mlProba > 0.6
  const mlType     = reading?.fault_pred === 1 ? (reading as any).fault_type_pred ?? null : null
  const isNight    = (reading?.irradiance_wm2 ?? 0) < 10
  const ft         = FAULT_INFO[mlType ?? '']
  const soilingPct = Math.round((reading?.soiling ?? 0) * 100)

  const cardBorder = mlFault ? '1px solid #f44336' : soilingPct > 20 ? '1px solid #ffd600' : '1px solid var(--border)'
  const cardShadow = mlFault ? '0 0 20px rgba(244,67,54,0.15)' : 'none'

  let badgeText = loading ? '···' : isNight ? 'NOCHE' : 'OK'
  let badgeBg = 'rgba(74,96,128,0.2)', badgeColor = 'var(--text-dim)', badgeBdr = 'var(--border)'
  if (mlFault && ft) {
    badgeText = ft.label.toUpperCase()
    badgeBg = ft.bg; badgeColor = ft.color; badgeBdr = ft.color + '66'
  } else if (mlFault) {
    // ML detecta falla pero no hay tipo clasificado aún
    badgeText = `FALLA ${Math.round(mlProba * 100)}%`
    badgeBg = 'rgba(244,67,54,0.15)'; badgeColor = '#f44336'; badgeBdr = 'rgba(244,67,54,0.3)'
  } else if (soilingPct > 20) {
    badgeText = `SUCIO ${soilingPct}%`
    badgeBg = 'rgba(255,214,0,0.15)'; badgeColor = '#ffd600'; badgeBdr = 'rgba(255,214,0,0.3)'
  } else if (!isNight && reading) {
    badgeBg = 'rgba(0,230,118,0.15)'; badgeColor = '#00e676'; badgeBdr = 'rgba(0,230,118,0.3)'
  }

  const metrics = [
    { label: 'P. AC',  value: reading ? reading.power_ac_kw!.toFixed(1)               : '–', unit: 'kW'   },
    { label: 'Irrad.', value: reading ? Math.round(reading.irradiance_wm2!).toString() : '–', unit: 'W/m²' },
    { label: 'T. Mod', value: reading ? reading.temp_module_c!.toFixed(1)              : '–', unit: '°C'   },
    { label: 'E. Hoy', value: reading ? reading.energy_daily_kwh!.toFixed(1)           : '–', unit: 'kWh'  },
  ]

  return (
    <div style={{
      background: 'var(--surface-2)', border: cardBorder, borderRadius: '8px',
      overflow: 'hidden', boxShadow: cardShadow, cursor: 'default',
      animation: mlFault ? 'fault-pulse 2s infinite' : 'none',
      display: 'flex', flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{
        padding: '10px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        borderBottom: '1px solid var(--border)', background: 'rgba(255,255,255,0.02)', gap: '6px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '7px', minWidth: 0 }}>
          <span
            onClick={onWeatherSelect}
            title="Ver clima de esta planta"
            style={{
              fontFamily: 'Syne, sans-serif', fontWeight: 600, fontSize: '0.82rem',
              whiteSpace: 'nowrap', cursor: 'pointer',
              color: isWeatherActive ? '#f59e0b' : 'inherit',
              borderBottom: isWeatherActive ? '1px solid rgba(245,158,11,0.5)' : '1px solid transparent',
              transition: 'color 0.15s, border-color 0.15s',
            }}
          >
            P{meta.id} · {meta.name}
          </span>
          <span style={{
            fontSize: '0.55rem', background: 'var(--border)', padding: '2px 6px',
            borderRadius: '3px', color: 'var(--text-dim)', letterSpacing: '0.06em', flexShrink: 0,
          }}>{meta.location}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
          <span style={{
            fontSize: '0.58rem', padding: '2px 8px', borderRadius: '3px',
            letterSpacing: '0.07em', fontWeight: 700, textTransform: 'uppercase',
            background: badgeBg, color: badgeColor, border: `1px solid ${badgeBdr}`,
          }}>{badgeText}</span>
          {/* Botón Dashboard */}
          <button
            onClick={(e) => { e.stopPropagation(); onDashboard() }}
            title={`Ver dashboard de ${meta.name}`}
            style={{
              background: 'rgba(88,166,255,0.08)', border: '1px solid rgba(88,166,255,0.3)',
              color: '#58a6ff', borderRadius: '3px', padding: '2px 8px',
              fontSize: '0.55rem', fontFamily: 'JetBrains Mono, monospace',
              cursor: 'pointer', letterSpacing: '0.04em', whiteSpace: 'nowrap',
            }}
          >
            📊
          </button>
        </div>
      </div>

      {/* Panel array + metrics */}
      <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
        <PanelArray reading={reading} meta={meta} />

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: '5px' }}>
          {metrics.map(m => (
            <div key={m.label} style={{
              background: 'var(--bg)', border: '1px solid var(--border)',
              borderRadius: '4px', padding: '6px 8px',
            }}>
              <div style={{ fontSize: '0.52rem', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '3px' }}>{m.label}</div>
              <div style={{ fontSize: '0.9rem', fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', lineHeight: 1 }}>{m.value}</div>
              <div style={{ fontSize: '0.52rem', color: 'var(--text-dim)', marginTop: '2px' }}>{m.unit}</div>
            </div>
          ))}
        </div>

        {/* Sparkline */}
        <div style={{
          height: '44px', background: 'var(--bg)', borderRadius: '4px',
          border: '1px solid var(--border)', overflow: 'hidden', position: 'relative',
        }}>
          <span style={{
            position: 'absolute', top: '3px', left: '6px', fontSize: '0.52rem',
            color: 'var(--text-dim)', zIndex: 2, letterSpacing: '0.07em', textTransform: 'uppercase',
          }}>kW</span>
          <Sparkline history={history} maxKw={meta.capacity_kw} />
        </div>
      </div>

      {/* Inversores */}
      <InverterRow reading={reading} meta={meta} />

      {/* ML badge */}
      <MlBadge reading={reading} />

      {/* Fault footer — info del ML, no del simulador */}
      <div style={{
        padding: '6px 10px', borderTop: '1px solid var(--border)', fontSize: '0.62rem',
        minHeight: '28px', display: 'flex', alignItems: 'center', gap: '6px',
      }}>
        {mlFault && ft ? (
          <>
            <span style={{ fontSize: '12px', flexShrink: 0 }}>{ft.icon}</span>
            <span style={{ color: ft.color }}>{ft.label}</span>
            <span style={{ color: 'var(--text-dim)', marginLeft: '4px' }}>· ML {Math.round(mlProba * 100)}%</span>
          </>
        ) : mlFault ? (
          <>
            <span style={{ fontSize: '12px' }}>⚠</span>
            <span style={{ color: '#f44336' }}>Anomalía detectada</span>
            <span style={{ color: 'var(--text-dim)', marginLeft: '4px' }}>· {Math.round(mlProba * 100)}% prob.</span>
          </>
        ) : soilingPct > 5 ? (
          <>
            <span style={{ fontSize: '12px' }}>🟫</span>
            <span style={{ color: '#ffd600' }}>Suciedad estimada {soilingPct}%{soilingPct > 20 ? ' · Limpiar' : ''}</span>
          </>
        ) : (
          <span style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>
            {loading ? 'Conectando...' : isNight ? 'Sin generación.' : 'Operando normalmente.'}
          </span>
        )}
      </div>
    </div>
  )
}

// ── Summary Strip ─────────────────────────────────────────────────────────────

function SummaryStrip({ data }: { data: Record<number, LivePlantData> }) {
  const valid       = Object.values(data)
  const totalPow    = valid.reduce((s, r) => s + (r.power_ac_kw ?? 0), 0)
  const totalEnergy = valid.reduce((s, r) => s + (r.energy_daily_kwh ?? 0), 0)
  const faultCount  = valid.filter(r => (r.fault_proba ?? 0) > 0.6).length
  const totalCap    = PLANT_META.reduce((s, m) => s + m.capacity_kw, 0)
  const capFactor   = totalCap > 0 ? (totalPow / totalCap * 100) : 0

  return (
    <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
      {[
        { label: 'Potencia Total', value: totalPow.toFixed(1) + ' kW',       color: '#f59e0b' },
        { label: 'Energía Hoy',    value: totalEnergy.toFixed(1) + ' kWh',   color: undefined  },
        { label: 'Cap. Factor',    value: capFactor.toFixed(1) + '%',         color: capFactor > 60 ? '#3fb950' : '#f59e0b' },
        { label: 'Fallas Activas', value: String(faultCount),                 color: faultCount > 0 ? '#f85149' : '#3fb950' },
        { label: 'Online',         value: `${valid.length} / ${PLANT_META.length}`, color: undefined },
      ].map(s => (
        <div key={s.label} style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontSize: '0.58rem', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{s.label}</span>
          <span style={{ fontSize: '1.0rem', fontWeight: 700, fontFamily: 'Syne, sans-serif', color: s.color ?? 'var(--text)' }}>{s.value}</span>
        </div>
      ))}
    </div>
  )
}

// ── Fault Log — lee desde DB via /dashboard/events ───────────────────────────

const HOURS_OPTIONS = [
  { label: '2h',    value: 2   },
  { label: '24h',   value: 24  },
  { label: '7d',    value: 168 },
  { label: 'Todo',  value: null },
]

function FaultLog({ selectedPlant }: { selectedPlant: number }) {
  const [events, setEvents]     = useState<FaultEvent[]>([])
  const [loading, setLoading]   = useState(false)
  const [hours, setHours]       = useState<number | null>(24)
  const logRef = useRef<HTMLDivElement>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchFaultEvents(selectedPlant, hours)
      setEvents(data)
    } catch {
      setEvents([])
    } finally {
      setLoading(false)
    }
  }, [selectedPlant, hours])

  useEffect(() => { load() }, [load])
  // Auto-refresh cada 30s
  useEffect(() => {
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [load])

  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--border)',
      borderRadius: '8px', overflow: 'hidden', marginTop: '20px',
    }}>
      {/* Header */}
      <div style={{
        padding: '10px 16px', borderBottom: '1px solid var(--border)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        background: 'rgba(255,255,255,0.02)', flexWrap: 'wrap', gap: '8px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 600, fontSize: '0.85rem' }}>
            📋 Log de Eventos ML
          </span>
          {events.length > 0 && (
            <span style={{
              fontSize: '0.60rem', background: 'rgba(244,67,54,0.15)', color: '#f44336',
              border: '1px solid rgba(244,67,54,0.3)', padding: '2px 8px', borderRadius: '10px',
            }}>{events.length}</span>
          )}
          <span style={{ fontSize: '0.58rem', color: 'var(--text-dim)', fontStyle: 'italic' }}>
            DB · inferencia ML
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          {/* Selector de período */}
          {HOURS_OPTIONS.map(opt => (
            <button
              key={String(opt.value)}
              onClick={() => setHours(opt.value)}
              style={{
                background: hours === opt.value ? 'rgba(88,166,255,0.15)' : 'transparent',
                border: `1px solid ${hours === opt.value ? 'rgba(88,166,255,0.5)' : 'var(--border)'}`,
                color: hours === opt.value ? '#58a6ff' : 'var(--text-dim)',
                borderRadius: '4px', padding: '2px 8px', fontSize: '0.6rem',
                fontFamily: 'JetBrains Mono, monospace', cursor: 'pointer',
              }}
            >{opt.label}</button>
          ))}
          <button onClick={load} style={{
            background: 'transparent', border: '1px solid var(--border)', color: 'var(--text-dim)',
            borderRadius: '4px', padding: '2px 8px', fontSize: '0.6rem',
            fontFamily: 'JetBrains Mono, monospace', cursor: 'pointer',
          }}>↻</button>
        </div>
      </div>

      {/* Body */}
      <div ref={logRef} style={{ maxHeight: '200px', overflowY: 'auto', padding: '4px 0' }}>
        {loading ? (
          <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-dim)', fontSize: '0.68rem' }}>
            Cargando...
          </div>
        ) : events.length === 0 ? (
          <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-dim)', fontSize: '0.72rem', fontStyle: 'italic' }}>
            Sin eventos de falla en el período seleccionado.
          </div>
        ) : events.map((e, i) => {
          const ft       = FAULT_INFO[e.fault_type ?? '']
          const isStart  = e.event_type === 'fault_start'
          const rowColor = isStart ? (ft?.color ?? '#f44336') : '#3fb950'
          const icon     = isStart ? (ft?.icon ?? '⚠') : '✓'
          const proba    = e.fault_proba != null ? `${Math.round(e.fault_proba * 100)}%` : ''
          const ts       = new Date(e.ts).toLocaleString('es-CO', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })

          return (
            <div key={i} style={{
              display: 'grid', gridTemplateColumns: '130px 1fr auto',
              gap: '10px', padding: '5px 16px', fontSize: '0.65rem',
              borderBottom: '1px solid rgba(30,45,61,0.5)',
            }}>
              <span style={{ color: 'var(--text-dim)' }}>{ts}</span>
              <span style={{ color: rowColor }}>{icon} {e.msg}</span>
              <span style={{ color: 'var(--text-dim)', textAlign: 'right', fontSize: '0.6rem' }}>{proba}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

interface Props {
  onSelectPlant: (plantId: number) => void
}

export default function PlantGrid({ onSelectPlant }: Props) {
  const { data: liveData, connected } = useLiveWeather()
  const [histories, setHistories]   = useState<Record<number, number[]>>({})
  const [weatherPlant, setWeatherPlant] = useState<number>(1)

  // Acumular sparkline history
  useEffect(() => {
    for (const r of Object.values(liveData)) {
      setHistories(prev => ({
        ...prev,
        [r.plant_id]: [...(prev[r.plant_id] ?? []).slice(-47), r.power_ac_kw ?? 0],
      }))
    }
  }, [liveData])

  const loading = Object.keys(liveData).length === 0

  return (
    <div style={{ maxWidth: '1600px', margin: '0 auto', padding: '20px 24px' }}>

      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end',
        marginBottom: '16px', borderBottom: '1px solid var(--border)', paddingBottom: '14px',
        gap: '16px', flexWrap: 'wrap',
      }}>
        <div>
          <h1 style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: '1.2rem', letterSpacing: '-0.02em', color: '#fff', margin: 0 }}>
            PLANTAS SOLARES
          </h1>
          <p style={{ fontSize: '0.62rem', color: 'var(--text-dim)', marginTop: '4px', letterSpacing: '0.06em', display: 'flex', alignItems: 'center', gap: '6px' }}>
            MONITOREO EN TIEMPO REAL · SSE
            <span style={{
              width: '6px', height: '6px', borderRadius: '50%', display: 'inline-block',
              background: connected ? '#3fb950' : '#f85149',
            }} />
            {connected ? 'CONECTADO' : 'RECONECTANDO...'}
          </p>
        </div>
        <SummaryStrip data={liveData} />
      </div>

      {/* Weather bar por planta */}
      <WeatherBar data={liveData} selectedId={weatherPlant} onSelect={setWeatherPlant} />

      {/* Grid 4×2 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: '14px' }}>
        {PLANT_META.map((meta) => (
          <PlantCard
            key={meta.id}
            meta={meta}
            reading={liveData[meta.id] ?? null}
            history={histories[meta.id] ?? []}
            loading={loading}
            onDashboard={() => onSelectPlant(meta.id)}
            onWeatherSelect={() => setWeatherPlant(meta.id)}
            isWeatherActive={weatherPlant === meta.id}
          />
        ))}
      </div>

      {/* Fault log — lee desde DB, persiste entre navegaciones */}
      <FaultLog selectedPlant={weatherPlant} />

      <style>{`
        @keyframes fault-pulse {
          0%,100% { box-shadow: 0 0 20px rgba(244,67,54,0.15); }
          50%      { box-shadow: 0 0 35px rgba(244,67,54,0.30); }
        }
        @keyframes slide-in {
          from { opacity: 0; transform: translateX(-8px); }
          to   { opacity: 1; transform: translateX(0); }
        }
      `}</style>
    </div>
  )
}