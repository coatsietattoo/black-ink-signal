import { useState, useEffect } from 'react'

const API = 'http://127.0.0.1:8787'

interface SetupStatus {
  api_reachable: boolean
  reddit_oauth: boolean
  database_exists: boolean
  has_leads: boolean
  scheduler_configured: boolean
}

export function OnboardingScreen({ onDismiss }: { onDismiss: () => void }) {
  const [status, setStatus] = useState<SetupStatus>({
    api_reachable: false,
    reddit_oauth: false,
    database_exists: false,
    has_leads: false,
    scheduler_configured: false,
  })
  const [loading, setLoading] = useState(true)
  const [seeding, setSeeding] = useState(false)

  useEffect(() => {
    checkStatus()
  }, [])

  const checkStatus = async () => {
    setLoading(true)
    try {
      const healthRes = await fetch(`${API}/health`)
      const health = await healthRes.json()

      const sourceRes = await fetch(`${API}/sources/health`)
      const sources = await sourceRes.json()

      setStatus({
        api_reachable: health.status === 'ok',
        reddit_oauth: sources.reddit?.oauth_configured || false,
        database_exists: true,
        has_leads: (sources.database?.total_leads || 0) > 0,
        scheduler_configured: true,
      })
    } catch {
      setStatus(prev => ({ ...prev, api_reachable: false }))
    } finally {
      setLoading(false)
    }
  }

  const seedData = async () => {
    setSeeding(true)
    try {
      await fetch(`${API}/admin/seed`, { method: 'POST' })
      await checkStatus()
    } catch {} finally {
      setSeeding(false)
    }
  }

  const allGood = status.api_reachable && status.reddit_oauth && status.has_leads

  return (
    <div className="onboarding">
      <div className="onboarding__card">
        <div className="onboarding__header">
          <span className="brand__icon">◆</span>
          <h1>Black Ink Signal</h1>
          <p className="onboarding__subtitle">Lead intelligence for tattoo studios</p>
        </div>

        <div className="onboarding__checklist">
          <h3>Setup Checklist</h3>

          <div className={`onboarding__item ${status.api_reachable ? 'onboarding__item--done' : 'onboarding__item--pending'}`}>
            <span className="onboarding__check">{status.api_reachable ? '✓' : '○'}</span>
            <div>
              <div className="onboarding__item-title">API Server</div>
              <div className="onboarding__item-desc">
                {status.api_reachable ? 'Running on port 8787' : 'Start: uvicorn app.main:app --port 8787'}
              </div>
            </div>
          </div>

          <div className={`onboarding__item ${status.reddit_oauth ? 'onboarding__item--done' : 'onboarding__item--warn'}`}>
            <span className="onboarding__check">{status.reddit_oauth ? '✓' : '!'}</span>
            <div>
              <div className="onboarding__item-title">Reddit OAuth</div>
              <div className="onboarding__item-desc">
                {status.reddit_oauth ? 'Credentials configured' : (
                  <>
                    Add to <code>.env</code>:
                    <pre className="onboarding__code">
{`BIS_REDDIT_CLIENT_ID=your_id
BIS_REDDIT_CLIENT_SECRET=your_secret
BIS_REDDIT_USERNAME=your_user
BIS_REDDIT_PASSWORD=your_pass`}
                    </pre>
                    <a href="https://www.reddit.com/prefs/apps" target="_blank" rel="noopener">
                      Create Reddit app →
                    </a>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className={`onboarding__item ${status.has_leads ? 'onboarding__item--done' : 'onboarding__item--pending'}`}>
            <span className="onboarding__check">{status.has_leads ? '✓' : '○'}</span>
            <div>
              <div className="onboarding__item-title">Lead Data</div>
              <div className="onboarding__item-desc">
                {status.has_leads ? 'Leads in database' : (
                  <button className="onboarding__seed-btn" onClick={seedData} disabled={seeding || !status.api_reachable}>
                    {seeding ? 'Seeding...' : '🌱 Seed demo data to get started'}
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className={`onboarding__item ${status.scheduler_configured ? 'onboarding__item--done' : 'onboarding__item--pending'}`}>
            <span className="onboarding__check">{status.scheduler_configured ? '✓' : '○'}</span>
            <div>
              <div className="onboarding__item-title">Scheduler</div>
              <div className="onboarding__item-desc">
                {status.scheduler_configured ? 'Configured (start separately: python3 app/scheduler.py)' : 'Not configured'}
              </div>
            </div>
          </div>
        </div>

        <div className="onboarding__actions">
          <button className="onboarding__btn" onClick={checkStatus} disabled={loading}>
            {loading ? '⟳ Checking...' : '↻ Re-check'}
          </button>
          {(status.api_reachable && status.has_leads) && (
            <button className="onboarding__btn onboarding__btn--primary" onClick={onDismiss}>
              {allGood ? 'Launch →' : 'Continue anyway →'}
            </button>
          )}
        </div>

        {!allGood && status.api_reachable && status.has_leads && (
          <p className="onboarding__note">
            You can continue without Reddit OAuth — the app works with seed data. Add credentials later for live leads.
          </p>
        )}
      </div>
    </div>
  )
}
