import { useState, useEffect, useCallback, useRef } from 'react'
import { LeadCard } from './components/LeadCard'
import { LeadDrawer } from './components/LeadDrawer'
import { Sidebar } from './components/Sidebar'
import { Header } from './components/Header'
import { AdminPanel } from './components/AdminPanel'
import { OnboardingScreen } from './components/OnboardingScreen'
import type { Lead, Filters, AppPrefs } from './types'
import './styles.css'

const API = 'http://127.0.0.1:8787'
const PREFS_KEY = 'bis_prefs'

function loadPrefs(): AppPrefs {
  try {
    const raw = localStorage.getItem(PREFS_KEY)
    if (raw) return JSON.parse(raw)
  } catch {}
  return {
    compactMode: false,
    view: 'feed',
    filters: { minScore: 0, status: null, bookmarkedOnly: false, search: '' },
    selectedLeadId: null,
    soundEnabled: true,
  }
}

function savePrefs(prefs: Partial<AppPrefs>) {
  try {
    const current = loadPrefs()
    localStorage.setItem(PREFS_KEY, JSON.stringify({ ...current, ...prefs }))
  } catch {}
}

export function App() {
  const prefs = loadPrefs()
  const [leads, setLeads] = useState<Lead[]>([])
  const [selected, setSelected] = useState<Lead | null>(null)
  const [filters, setFilters] = useState<Filters>(prefs.filters)
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState({ total: 0, hot: 0, strong: 0, watchlist: 0 })
  const [notificationsEnabled, setNotificationsEnabled] = useState(true)
  const [view, setView] = useState<'feed' | 'admin'>(prefs.view)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)
  const [compactMode, setCompactMode] = useState(prefs.compactMode)
  const [soundEnabled, setSoundEnabled] = useState(prefs.soundEnabled)
  const [newLeadIds, setNewLeadIds] = useState<Set<number>>(new Set())
  const [ticker, setTicker] = useState<string[]>([])
  const prevLeadIdsRef = useRef<Set<number>>(new Set())

  // Persist prefs
  useEffect(() => { savePrefs({ filters }) }, [filters])
  useEffect(() => { savePrefs({ view }) }, [view])
  useEffect(() => { savePrefs({ compactMode }) }, [compactMode])
  useEffect(() => { savePrefs({ soundEnabled }) }, [soundEnabled])
  useEffect(() => {
    savePrefs({ selectedLeadId: selected?.id ?? null })
  }, [selected])

  const fetchLeads = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (filters.minScore > 0) params.set('min_score', String(filters.minScore))
      if (filters.status) params.set('status', filters.status)
      if (filters.bookmarkedOnly) params.set('bookmarked_only', 'true')
      params.set('limit', '200')

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

      // Detect new leads for animation
      const currentIds = new Set(data.map(l => l.id))
      const prevIds = prevLeadIdsRef.current
      const freshIds = new Set<number>()
      data.forEach(l => {
        if (!prevIds.has(l.id)) freshIds.add(l.id)
      })
      if (freshIds.size > 0 && prevIds.size > 0) {
        setNewLeadIds(freshIds)
        // Ticker update
        const freshLeads = data.filter(l => freshIds.has(l.id))
        const tickerLines = freshLeads.slice(0, 3).map(l =>
          `${l.score_band === 'hot' ? '🔥' : '◆'} ${l.lead_score} — ${(l.title || '').slice(0, 50)}`
        )
        setTicker(prev => [...tickerLines, ...prev].slice(0, 8))

        // Sound for hot leads
        if (soundEnabled && freshLeads.some(l => l.lead_score >= 80)) {
          playNotificationSound()
        }

        // Clear animation after delay
        setTimeout(() => setNewLeadIds(new Set()), 3000)
      }
      prevLeadIdsRef.current = currentIds

      setLeads([...data].sort((a, b) => b.id - a.id))
      setApiError(null)

      // Restore selected lead from prefs on first load
      if (!selected && prefs.selectedLeadId) {
        const restored = data.find(l => l.id === prefs.selectedLeadId)
        if (restored) setSelected(restored)
      }
    } catch (e: any) {
      setApiError(e.message || 'Cannot reach API')
    } finally {
      setLoading(false)
    }
  }, [filters, soundEnabled])

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API}/stats`)
      setStats(await res.json())
    } catch {}
  }, [])

  useEffect(() => { fetchLeads(); fetchStats() }, [fetchLeads, fetchStats])

  // Check if first run
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
    <div className={`app-shell ${compactMode ? 'app-shell--compact' : ''}`}>
      {apiError && (
        <div className="error-banner">
          <span className="error-banner__icon">⚠</span>
          <span>API unreachable: {apiError}</span>
          <button className="error-banner__btn" onClick={() => { fetchLeads(); fetchStats() }}>Retry</button>
        </div>
      )}
      <Sidebar
        stats={stats}
        filters={filters}
        onFiltersChange={setFilters}
        view={view}
        onViewChange={setView}
        compactMode={compactMode}
        onCompactToggle={() => setCompactMode(c => !c)}
        soundEnabled={soundEnabled}
        onSoundToggle={() => setSoundEnabled(s => !s)}
      />
      <div className="main-area">
        <Header
          leadCount={leads.length}
          loading={loading}
          onRefresh={() => { fetchLeads(); fetchStats() }}
          search={filters.search}
          onSearchChange={(s) => setFilters(f => ({ ...f, search: s }))}
          notificationsEnabled={notificationsEnabled}
          onNotificationsToggle={() => setNotificationsEnabled(e => !e)}
          compactMode={compactMode}
        />

        {/* Activity ticker */}
        {ticker.length > 0 && !compactMode && (
          <div className="activity-ticker">
            {ticker.map((line, i) => (
              <span key={i} className="ticker-item">{line}</span>
            ))}
          </div>
        )}

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
                    isNew={newLeadIds.has(lead.id)}
                    compactMode={compactMode}
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

// Minimal notification sound (Web Audio API)
function playNotificationSound() {
  try {
    const ctx = new AudioContext()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.frequency.value = 880
    osc.type = 'sine'
    gain.gain.setValueAtTime(0.1, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3)
    osc.start(ctx.currentTime)
    osc.stop(ctx.currentTime + 0.3)
  } catch {}
}
