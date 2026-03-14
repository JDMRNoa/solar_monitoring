type Page = 'dashboard' | 'plants' | 'control'

interface NavbarProps {
  lastUpdated: string | null
  currentPage: Page
  role: string | null
  onNavigate: (page: Page) => void
  onLogout: () => void
}

export default function Navbar({ lastUpdated, currentPage, role, onNavigate, onLogout }: NavbarProps) {
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

        {/* Nav tabs */}
        <nav style={{ display: 'flex', gap: '4px' }}>
          {([
            {
              id: 'plants',
              label: 'PLANT GRID',
              icon: (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <rect width="7" height="7" x="3" y="3" rx="1" /><rect width="7" height="7" x="14" y="3" rx="1" /><rect width="7" height="7" x="14" y="14" rx="1" /><rect width="7" height="7" x="3" y="14" rx="1" />
                </svg>
              )
            },
            {
              id: 'dashboard',
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
          ]).map(tab => {
            const active = currentPage === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => onNavigate(tab.id as Page)}
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

        {/* Right side (Update & Logout) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
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
      </div>
    </header>
  )
}