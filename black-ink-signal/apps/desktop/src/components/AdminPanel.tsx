import { useState, useEffect, useCallback } from 'react'

const API = 'http://127.0.0.1:8787'

interface SourceHealth {
  reddit: {
    oauth_configured: boolean
    connector_mode: string
    last_fetch: string | null
    last_fetch_status: string | null
    last_fetch_items_seen: number
    last_fetch_items_added: number
    last_fetch_errors: string | null
    runs_24h: number
    added_24h: number
    errors_24h: number
  }
  enrichment: {
    llm_configured: boolean
    mode: string
    pending: number
  }
  scheduler: {
    reddit_interval_min: number
    enrichment_interval_min: number
  }
  database: {
    total_leads: number
  }
}

interface DailySummary {
  date: string
  leads_today: number
  hot_today: number
  strong_today: number
  status_breakdown: Record<string, number>
  top_keywords: { keyword: string; count: number }[]
  top_sources: { source: string; count: number }[]
  top_intents: { intent: string; count: number }[]
}

interface Revenue {
  booked_count: number
  estimated_revenue: number
  breakdown: Record<string, number>
}

export function AdminPanel() {
  const [health, setHealth] = useState<SourceHealth | null>(null)
  const [daily, setDaily] = useState<DailySummary | null>(null)
  const [revenue, setRevenue] = useState<Revenue | null>(null)
  const [actionLog, setActionLog] = useState<string[]>([])
  const [loading, setLoading] = useState<string | null>(null)

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API}/sources/health`)
      setHealth(await res.json())
    } catch {}
  }, [])

  const fetchDaily = useCallback(async () => {
    try {
      const res = await fetch(`${API}/stats/daily`)
      setDaily(await res.json())
    } catch {}
    try {
      const res = await fetch(`${API}/stats/revenue`)
      setRevenue(await res.json())
    } catch {}
  }, [])

  useEffect(() => { fetchHealth(); fetchDaily() }, [fetchHealth, fetchDaily])
  useEffect(() => {
    const id = setInterval(() => { fetchHealth(); fetchDaily() }, 30_000)
    return () => clearInterval(id)
  }, [fetchHealth, fetchDaily])

  const runAction = async (endpoint: string, method: string, label: string) => {
    setLoading(label)
    try {
      const res = await fetch(`${API}${endpoint}`, { method })
      const data = await res.json()
      setActionLog(prev => [`[${new Date().toLocaleTimeString()}] ${label}: ${JSON.stringify(data)}`, ...prev.slice(0, 9)])
      fetchHealth()
      fetchDaily()
    } catch (e) {
      setActionLog(prev => [`[${new Date().toLocaleTimeString()}] ${label}: ERROR`, ...prev.slice(0, 9)])
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className="admin-panel">
      {/* Source Health */}
      <div className="admin-section">
        <h3 className="admin-section__title">Source Health</h3>
        {health && (
          <div className="health-grid">
            <div className="health-card">
              <div className="health-card__header">
                <span className={`health-dot ${health.reddit.oauth_configured ? 'health-dot--green' : 'health-dot--yellow'}`} />
                Reddit
              </div>
              <div className="health-card__body">
                <div className="health-row">
                  <span>Mode</span>
                  <span className="health-value">{health.reddit.connector_mode}</span>
                </div>
                <div className="health-row">
                  <span>OAuth</span>
                  <span className={`health-value ${health.reddit.oauth_configured ? 'health-value--ok' : 'health-value--warn'}`}>
                    {health.reddit.oauth_configured ? '✓ configured' : '✗ missing'}
                  </span>
                </div>
                <div className="health-row">
                  <span>Last fetch</span>
                  <span className="health-value">
                    {health.reddit.last_fetch ? new Date(health.reddit.last_fetch).toLocaleTimeString() : '—'}
                    {health.reddit.last_fetch_status && ` (${health.reddit.last_fetch_status})`}
                  </span>
                </div>
                <div className="health-row">
                  <span>Items (last)</span>
                  <span className="health-value">{health.reddit.last_fetch_items_seen} seen / {health.reddit.last_fetch_items_added} added</span>
                </div>
                <div className="health-row">
                  <span>24h</span>
                  <span className="health-value">{health.reddit.runs_24h} runs · {health.reddit.added_24h} added · {health.reddit.errors_24h} errors</span>
                </div>
              </div>
            </div>

            <div className="health-card">
              <div className="health-card__header">
                <span className={`health-dot ${health.enrichment.pending === 0 ? 'health-dot--green' : 'health-dot--yellow'}`} />
                Enrichment
              </div>
              <div className="health-card__body">
                <div className="health-row">
                  <span>Mode</span>
                  <span className="health-value">{health.enrichment.mode}</span>
                </div>
                <div className="health-row">
                  <span>LLM</span>
                  <span className={`health-value ${health.enrichment.llm_configured ? 'health-value--ok' : ''}`}>
                    {health.enrichment.llm_configured ? '✓ configured' : 'rule-based only'}
                  </span>
                </div>
                <div className="health-row">
                  <span>Pending</span>
                  <span className="health-value">{health.enrichment.pending} leads</span>
                </div>
              </div>
            </div>

            <div className="health-card">
              <div className="health-card__header">
                <span className="health-dot health-dot--green" />
                Scheduler
              </div>
              <div className="health-card__body">
                <div className="health-row">
                  <span>Reddit poll</span>
                  <span className="health-value">every {health.scheduler.reddit_interval_min}m</span>
                </div>
                <div className="health-row">
                  <span>Enrichment</span>
                  <span className="health-value">every {health.scheduler.enrichment_interval_min}m</span>
                </div>
                <div className="health-row">
                  <span>Database</span>
                  <span className="health-value">{health.database.total_leads} leads</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Daily Summary */}
      {daily && (
        <div className="admin-section">
          <h3 className="admin-section__title">Daily Summary ({daily.date})</h3>
          <div className="daily-grid">
            <div className="daily-stat">
              <span className="daily-stat__value">{daily.leads_today}</span>
              <span className="daily-stat__label">leads today</span>
            </div>
            <div className="daily-stat daily-stat--hot">
              <span className="daily-stat__value">{daily.hot_today}</span>
              <span className="daily-stat__label">hot</span>
            </div>
            <div className="daily-stat daily-stat--strong">
              <span className="daily-stat__value">{daily.strong_today}</span>
              <span className="daily-stat__label">strong</span>
            </div>
            {Object.entries(daily.status_breakdown).map(([status, count]) => (
              <div key={status} className="daily-stat">
                <span className="daily-stat__value">{count}</span>
                <span className="daily-stat__label">{status}</span>
              </div>
            ))}
          </div>

          {daily.top_keywords.length > 0 && (
            <div className="daily-list">
              <div className="daily-list__title">Top Keywords</div>
              {daily.top_keywords.slice(0, 5).map(k => (
                <div key={k.keyword} className="daily-list__item">
                  <span>{k.keyword}</span>
                  <span className="daily-list__count">{k.count}</span>
                </div>
              ))}
            </div>
          )}

          {daily.top_sources.length > 0 && (
            <div className="daily-list">
              <div className="daily-list__title">Top Sources</div>
              {daily.top_sources.map(s => (
                <div key={s.source} className="daily-list__item">
                  <span>r/{s.source}</span>
                  <span className="daily-list__count">{s.count}</span>
                </div>
              ))}
            </div>
          )}

          {revenue && revenue.booked_count > 0 && (
            <div className="daily-list">
              <div className="daily-list__title">Revenue (Booked)</div>
              <div className="daily-list__item">
                <span>Booked leads</span>
                <span className="daily-list__count">{revenue.booked_count}</span>
              </div>
              <div className="daily-list__item">
                <span>Estimated revenue</span>
                <span className="daily-list__count">${revenue.estimated_revenue.toLocaleString()}</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Admin Actions */}
      <div className="admin-section">
        <h3 className="admin-section__title">Actions</h3>
        <div className="admin-actions">
          <button className="admin-btn" onClick={() => runAction('/admin/fetch-reddit', 'POST', 'Reddit Fetch')} disabled={!!loading}>
            {loading === 'Reddit Fetch' ? '⟳' : '↻'} Fetch Reddit Now
          </button>
          <button className="admin-btn" onClick={() => runAction('/admin/enrich?limit=50', 'POST', 'Enrich')} disabled={!!loading}>
            {loading === 'Enrich' ? '⟳' : '🧠'} Enrich Leads
          </button>
          <button className="admin-btn" onClick={() => runAction('/admin/rescore', 'POST', 'Rescore')} disabled={!!loading}>
            📊 Rescore All
          </button>
          <button className="admin-btn" onClick={() => runAction('/admin/seed', 'POST', 'Seed')} disabled={!!loading}>
            🌱 Seed Demo Data
          </button>
          <button className="admin-btn" onClick={() => runAction('/export/csv?min_score=0', 'GET', 'Export')} disabled={!!loading}>
            📄 Export CSV
          </button>
          <button className="admin-btn admin-btn--danger" onClick={() => runAction('/admin/clear-demo', 'DELETE', 'Clear Demo')} disabled={!!loading}>
            🗑 Clear Demo Data
          </button>
          <button className="admin-btn" onClick={() => runAction('/admin/backup', 'POST', 'Backup')} disabled={!!loading}>
            💾 Backup Database
          </button>
          <button className="admin-btn" onClick={() => window.open(`${API}/admin/backup/download`, '_blank')} disabled={!!loading}>
            ⬇ Download DB
          </button>
          <button className="admin-btn" onClick={() => runAction('/admin/dedup-report', 'GET', 'Dedup Report')} disabled={!!loading}>
            🔍 Dedup Report
          </button>
        </div>
      </div>

      {/* Action Log */}
      {actionLog.length > 0 && (
        <div className="admin-section">
          <h3 className="admin-section__title">Log</h3>
          <div className="action-log">
            {actionLog.map((line, i) => (
              <div key={i} className="action-log__line">{line}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
