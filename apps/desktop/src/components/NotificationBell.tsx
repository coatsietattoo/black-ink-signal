import { useState, useEffect, useCallback } from 'react'

const API = 'http://127.0.0.1:8787'

interface Notification {
  id: number
  score: number
  title: string
  geo: string | null
  label: string | null
  url: string | null
  timestamp: string
}

interface Props {
  enabled: boolean
  onToggle: () => void
}

export function NotificationBell({ enabled, onToggle }: Props) {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [showPanel, setShowPanel] = useState(false)
  const [pulse, setPulse] = useState(false)
  const [lastCount, setLastCount] = useState(0)

  const fetchNotifications = useCallback(async () => {
    if (!enabled) return
    try {
      const res = await fetch(`${API}/notifications?limit=10`)
      const data: Notification[] = await res.json()
      setNotifications(data)

      // Pulse if new notifications
      if (data.length > lastCount && lastCount > 0) {
        setPulse(true)
        // Play sound if available
        try {
          const audio = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdH+Jk4yGfnR1fYiQjIaAeXV4gImOjIV/eXV5gYqPjYaAeXZ5gYqOjIZ/eXV6gYqOjIV/eHV5gImOjIZ+eHV5gImOjIV+eHV5gImOjIV+eHV5gImNi4V9d3R4f4iMioN8d3N4foeLiYJ7dnN3fYaKiIF6dXJ2fIWJh4B5dHF1e4SIhoB4c3B0eoKHhX93cnBzeoGGhH92cW9yeb+DhH91cG9xeL+Cg351cG5xeL6BgX10b21wd7yAgHxzbmxvdruAf3tybWtudbiAf3tybWtudbiAf3tybWtudbiAf3tybWtudbiAf3tybWtudbiAf3tybWtudbiAfg==')
          audio.volume = 0.3
          audio.play().catch(() => {})
        } catch {}
        setTimeout(() => setPulse(false), 3000)
      }
      setLastCount(data.length)
    } catch {}
  }, [enabled, lastCount])

  useEffect(() => {
    fetchNotifications()
    const id = setInterval(fetchNotifications, 15_000)
    return () => clearInterval(id)
  }, [fetchNotifications])

  const hotCount = notifications.length

  return (
    <div className="notification-bell-wrapper">
      <button
        className={`notification-bell ${pulse ? 'notification-bell--pulse' : ''}`}
        onClick={() => setShowPanel(!showPanel)}
        title={enabled ? `${hotCount} hot leads` : 'Notifications off'}
      >
        🔔 {hotCount > 0 && <span className="notification-badge">{hotCount}</span>}
      </button>

      <button
        className={`notification-toggle ${enabled ? 'notification-toggle--on' : ''}`}
        onClick={onToggle}
        title={enabled ? 'Disable notifications' : 'Enable notifications'}
      >
        {enabled ? '🔊' : '🔇'}
      </button>

      {showPanel && (
        <div className="notification-panel">
          <div className="notification-panel__header">
            <span>Hot Leads ({hotCount})</span>
            <button onClick={() => setShowPanel(false)}>✕</button>
          </div>
          {notifications.length === 0 ? (
            <div className="notification-panel__empty">No hot lead alerts yet</div>
          ) : (
            notifications.map((n, i) => (
              <div key={`${n.id}-${i}`} className="notification-item">
                <span className="notification-item__score">{n.score}</span>
                <div className="notification-item__body">
                  <div className="notification-item__title">{n.title || 'Lead'}</div>
                  <div className="notification-item__meta">
                    {n.geo && <span>📍 {n.geo}</span>}
                    {n.label && <span>{n.label.replace(/_/g, ' ')}</span>}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
