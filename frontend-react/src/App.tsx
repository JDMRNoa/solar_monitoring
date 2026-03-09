import { useState, useEffect } from 'react'
import Navbar from './components/Navbar'
import Footer from './components/Footer'
import Dashboard from './pages/Dashboard'
import PlantGrid from './pages/PlantGrid'
import Control from './pages/Control'
import Login from './pages/Login'
import { setToken, removeToken, isAuthenticated, getRole } from './lib/auth'

type Page = 'dashboard' | 'plants' | 'control'

export default function App() {
  const [isAuth, setIsAuth]           = useState<boolean>(false)
  const [role, setRole]               = useState<string | null>(null)
  const [lastTs, setLastTs]           = useState<string | null>(null)
  
  // Start on 'plants' by default instead of dashboard
  const [page, setPage]               = useState<Page>('plants')
  const [selectedPlant, setSelectedPlant] = useState<number>(1)

  useEffect(() => {
    if (isAuthenticated()) {
      setIsAuth(true)
      setRole(getRole() || null)
    }
  }, [])

  const handleLogin = (token: string, userRole: string) => {
    setToken(token, userRole)
    setIsAuth(true)
    setRole(userRole)
    setPage('plants') // Default landing page
  }

  const handleLogout = () => {
    removeToken()
    setIsAuth(false)
    setRole(null)
  }

  // Navegar al dashboard con una planta específica desde PlantGrid
  function openDashboardForPlant(plantId: number) {
    setSelectedPlant(plantId)
    setPage('dashboard')
  }

  if (!isAuth) {
    return <Login onLoginSuccess={handleLogin} />
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar 
        lastUpdated={lastTs} 
        currentPage={page} 
        onNavigate={setPage} 
        role={role} 
        onLogout={handleLogout} 
      />
      <main className="flex-1">
        {page === 'dashboard' && (
          <Dashboard
            onLastTimestamp={setLastTs}
            initialPlantId={selectedPlant}
            onPlantChange={setSelectedPlant}
          />
        )}
        {page === 'plants' && (
          <PlantGrid onSelectPlant={openDashboardForPlant} />
        )}
        {page === 'control' && role === 'admin' && (
          <Control />
        )}
      </main>
      <Footer />
    </div>
  )
}