import { useState } from 'react'

type Page = 'dashboard' | 'plants' | 'control'

interface NavbarProps {
  lastUpdated: string | null
  currentPage: Page
  role: string | null
  onNavigate: (page: Page) => void
  onLogout: () => void
}

export default function Navbar({ lastUpdated, currentPage, role, onNavigate, onLogout }: NavbarProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false)

  const navItems = [
    {
      id: 'plants' as Page,
      label: 'PLANT GRID',
      icon: (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <rect width="7" height="7" x="3" y="3" rx="1" /><rect width="7" height="7" x="14" y="3" rx="1" /><rect width="7" height="7" x="14" y="14" rx="1" /><rect width="7" height="7" x="3" y="14" rx="1" />
        </svg>
      )
    },
    {
      id: 'dashboard' as Page,
      label: 'DASHBOARD',
      icon: (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="m12 14 4-4" /><path d="M3.34 19a10 10 0 1 1 17.32 0" />
        </svg>
      )
    },
    ...(role === 'admin' ? [{
      id: 'control' as Page,
      label: 'CONTROL',
      icon: (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .52 8.242 4.42 4.42 0 0 0 8.71 0 4 4 0 0 0 .52-8.242 4 4 0 0 0-2.526-5.77A3 3 0 0 0 12 5" />
          <path d="M9 13h4" /><path d="M12 10v6" />
        </svg>
      )
    }] : [])
  ]

  return (
    <header
      style={{
        background: 'var(--surface)',
        borderBottom: '1px solid var(--border)',
      }}
      className="sticky top-0 z-50"
    >
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="4" fill="#f59e0b" />
            <path
              d="M12 2v2M12 20v2M2 12h2M20 12h2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
              stroke="#f59e0b" strokeWidth="1.5" strokeLinecap="round"
            />
          </svg>
          <span style={{ fontFamily: 'Syne, sans-serif', color: '#fff', fontWeight: 700, fontSize: '1rem', letterSpacing: '0.05em' }}>
            SOLAR<span style={{ color: 'var(--solar)' }}>MONITOR</span>
          </span>
        </div>

        {/* Desktop Nav tabs */}
        <nav className="hidden md:flex gap-1">
          {navItems.map(tab => {
            const active = currentPage === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => onNavigate(tab.id)}
                style={{
                  background: active ? 'rgba(88, 166, 255, 0.1)' : 'transparent',
                  border: active ? '1px solid rgba(245,158,11,0.4)' : '1px solid transparent',
                  color: active ? '#f59e0b' : 'var(--text-dim)',
                  borderRadius: '4px',
                  padding: '5px 12px',
                  fontSize: '0.72rem',
                  fontFamily: 'JetBrains Mono, monospace',
                  letterSpacing: '0.05em',
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}
              >
                {tab.icon}
                {tab.label}
              </button>
            )
          })}
        </nav>

        {/* Right side (Update & Logout - Desktop) */}
        <div className="hidden md:flex items-center gap-4">
          {lastUpdated && (
            <span style={{ color: 'var(--text-dim)', fontSize: '0.7rem' }}>
              LAST UPDATE: {new Date(lastUpdated).toLocaleString()}
            </span>
          )}
          <button
            onClick={onLogout}
            style={{
              background: 'transparent',
              border: '1px solid var(--border)',
              color: 'var(--text-dim)',
              padding: '4px 12px',
              borderRadius: '4px',
              fontSize: '0.65rem',
              cursor: 'pointer',
              fontFamily: 'JetBrains Mono, monospace',
              transition: 'all 0.2s',
            }}
            onMouseOver={(e) => { e.currentTarget.style.color = '#ef4444'; e.currentTarget.style.borderColor = '#ef4444' }}
            onMouseOut={(e) => { e.currentTarget.style.color = 'var(--text-dim)'; e.currentTarget.style.borderColor = 'var(--border)' }}
          >
            LOGOUT
          </button>
        </div>

        {/* Mobile Menu Button */}
        <button
          className="md:hidden p-2 text-text-dim hover:text-white transition-colors"
          onClick={() => setIsMenuOpen(!isMenuOpen)}
        >
          {isMenuOpen ? (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          ) : (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="3" y1="12" x2="21" y2="12"></line>
              <line x1="3" y1="6" x2="21" y2="6"></line>
              <line x1="3" y1="18" x2="21" y2="18"></line>
            </svg>
          )}
        </button>
      </div>

      {/* Mobile Drawer Overlay */}
      {isMenuOpen && (
        <div className="md:hidden fixed inset-0 z-40 bg-black/60 backdrop-blur-sm" onClick={() => setIsMenuOpen(false)}>
          <nav
            className="absolute top-14 left-0 right-0 p-4 flex flex-col gap-2 border-b border-border shadow-2xl animate-in slide-in-from-top duration-200"
            style={{ background: 'var(--surface)' }}
            onClick={(e) => e.stopPropagation()}
          >
            {navItems.map(tab => {
              const active = currentPage === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => { onNavigate(tab.id); setIsMenuOpen(false) }}
                  className="flex items-center gap-3 px-4 py-3 rounded-md transition-all active:scale-95 text-left"
                  style={{
                    background: active ? 'var(--solar-dim)' : 'transparent',
                    border: active ? '1px solid var(--solar)' : '1px solid transparent',
                    color: active ? 'var(--solar)' : 'var(--text-dim)',
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: '0.85rem'
                  }}
                >
                  <span className={active ? 'text-solar' : 'text-text-dim'}>{tab.icon}</span>
                  {tab.label}
                </button>
              )
            })}
            <div className="h-px bg-border my-2" />
            {lastUpdated && (
              <div className="px-4 py-1 text-[10px] uppercase text-text-dim/60 tracking-widest font-mono">
                LAST UPDATE: {new Date(lastUpdated).toLocaleString()}
              </div>
            )}
            <button
              onClick={onLogout}
              className="flex items-center gap-3 px-4 py-3 text-red-500 font-mono text-sm hover:bg-red-500/10 rounded-md transition-colors"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                <polyline points="16 17 21 12 16 7"></polyline>
                <line x1="21" y1="12" x2="9" y2="12"></line>
              </svg>
              LOGOUT
            </button>
          </nav>
        </div>
      )}
    </header>
  )
}