import { useState, useEffect, useCallback } from 'react'
import { LeadCard } from './components/LeadCard'
import { LeadDrawer } from './components/LeadDrawer'
import { Sidebar } from './components/Sidebar'
import { Header } from './components/Header'
import { AdminPanel } from './components/AdminPanel'
import { OnboardingScreen } from './components/OnboardingScreen'
import type { Lead, Filters } from './types'
import './styles.css'

const API = 'http://127.0.0.1:8787'

export function App() {
  const [leads, setLeads] = useState<Lead[]>([])
  const [selected, setSelected] = useState<Lead | null>(null)
  const [filters, setFilters] = useState<Filters>({
    minScore: 0,
    status: null,
    bookmarkedOnly: false,
    search: '',
  })
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState({ total: 0, hot: 0, strong: 0, watchlist: 0 })
  const [notificationsEnabled, setNotificationsEnabled] = useState(true)
  const [view, setView] = useState<'feed' | 'admin'>('feed')
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)

  const fetchLeads = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (filters.minScore > 0) params.set('min_score', String(filters.minScore))
      if (filters.status) params.set('status', filters.status)
      if (filters.bookmarkedOnly) params.set('bookmarked_only', 'true')
      params.set('limit', '100')

      const res = await fetch(`${API}/leads?${params}`)
      if (!res.ok) throw new Error(`API returned ${res.status}`)
      let data: Lead[] = await res.json()

      if (filters.search) {
        const q = filters.search.toLowerCase()
        data = data.filter(l =>
          (l.title?.toLowerCase().includes(q)) ||
          (l.body?.toLowerCase().includes(q)) ||
          (l.author_handle?.toLowerCase().includes(q)) ||
          (l.keyword_trigger?.toLowerCase().includes(q))
        )
      }

      setLeads(data)
      setApiError(null)
    } catch (e: any) {
      setApiError(e.message || 'Cannot reach API')
    } finally {
      setLoading(false)
    }
  }, [filters])

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API}/stats`)
      setStats(await res.json())
    } catch {}
  }, [])

  useEffect(() => { fetchLeads(); fetchStats() }, [fetchLeads, fetchStats])

  // Check if first run (no leads and possible missing OAuth)
  useEffect(() => {
    const checkOnboarding = async () => {
      try {
        const res = await fetch(`${API}/sources/health`)
        const data = await res.json()
        const noOAuth = !data.reddit?.oauth_configured
        const noLeads = (data.database?.total_leads || 0) === 0
        if (noOAuth && noLeads) setShowOnboarding(true)
      } catch {
        setShowOnboarding(true)
      }
    }
    checkOnboarding()
  }, [])

  // Auto-refresh every 30s
  useEffect(() => {
    const id = setInterval(() => { fetchLeads(); fetchStats() }, 30_000)
    return () => clearInterval(id)
  }, [fetchLeads, fetchStats])

  const updateStatus = async (leadId: number, status: string) => {
    await fetch(`${API}/leads/${leadId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    })
    fetchLeads()
    if (selected?.id === leadId) {
      setSelected(prev => prev ? { ...prev, lead_status: status } : null)
    }
  }

  const toggleBookmark = async (leadId: number, current: boolean) => {
    await fetch(`${API}/leads/${leadId}/bookmark`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bookmarked: !current }),
    })
    fetchLeads()
    if (selected?.id === leadId) {
      setSelected(prev => prev ? { ...prev, bookmarked: !current } : null)
    }
  }

  const updateNotes = async (leadId: number, notes: string) => {
    await fetch(`${API}/leads/${leadId}/notes`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes }),
    })
  }

  if (showOnboarding) {
    return <OnboardingScreen onDismiss={() => { setShowOnboarding(false); fetchLeads(); fetchStats() }} />
  }

  return (
    <div className="app-shell">
      {apiError && (
        <div className="error-banner">
          <span className="error-banner__icon">⚠</span>
          <span>API unreachable: {apiError}</span>
          <button className="error-banner__btn" onClick={() => { fetchLeads(); fetchStats() }}>Retry</button>
        </div>
      )}
      <Sidebar stats={stats} filters={filters} onFiltersChange={setFilters} view={view} onViewChange={setView} />
      <div className="main-area">
        <Header
          leadCount={leads.length}
          loading={loading}
          onRefresh={() => { fetchLeads(); fetchStats() }}
          search={filters.search}
          onSearchChange={(s) => setFilters(f => ({ ...f, search: s }))}
          notificationsEnabled={notificationsEnabled}
          onNotificationsToggle={() => setNotificationsEnabled(e => !e)}
        />
        <div className="content-area">
          {view === 'admin' ? (
            <section className="feed">
              <AdminPanel />
            </section>
          ) : (
            <>
              <section className="feed">
                {leads.length === 0 && !loading && (
                  <div className="empty-state">
                    <h2>No leads match filters</h2>
                    <p>Adjust filters or wait for new data.</p>
                  </div>
                )}
                {leads.map(lead => (
                  <LeadCard
                    key={lead.id}
                    lead={lead}
                    isSelected={selected?.id === lead.id}
                    onSelect={() => setSelected(lead)}
                    onStatusChange={(s) => updateStatus(lead.id, s)}
                    onBookmark={() => toggleBookmark(lead.id, lead.bookmarked)}
                  />
                ))}
              </section>
              {selected && (
                <LeadDrawer
                  lead={selected}
                  onClose={() => setSelected(null)}
                  onStatusChange={(s) => updateStatus(selected.id, s)}
                  onBookmark={() => toggleBookmark(selected.id, selected.bookmarked)}
                  onNotesChange={(n) => updateNotes(selected.id, n)}
                />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
