import { useState } from 'react'
import Navbar from './components/Navbar'
import Footer from './components/Footer'
import Dashboard from './pages/Dashboard'
import PlantGrid from './pages/PlantGrid'

type Page = 'dashboard' | 'plants'

export default function App() {
  const [lastTs, setLastTs] = useState<string | null>(null)
  const [page, setPage] = useState<Page>('dashboard')

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar lastUpdated={lastTs} currentPage={page} onNavigate={setPage} />
      <main className="flex-1">
        {page === 'dashboard' && <Dashboard onLastTimestamp={setLastTs} />}
        {page === 'plants'    && <PlantGrid />}
      </main>
      <Footer />
    </div>
  )
}