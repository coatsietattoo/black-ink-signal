import { NotificationBell } from './NotificationBell'

interface Props {
  leadCount: number
  loading: boolean
  onRefresh: () => void
  search: string
  onSearchChange: (s: string) => void
  notificationsEnabled: boolean
  onNotificationsToggle: () => void
}

export function Header({ leadCount, loading, onRefresh, search, onSearchChange, notificationsEnabled, onNotificationsToggle }: Props) {
  return (
    <header className="feed-header">
      <div className="feed-header__left">
        <h1>Live Feed</h1>
        <span className="lead-count">{leadCount} leads</span>
      </div>
      <div className="feed-header__right">
        <input
          className="search-input"
          type="text"
          placeholder="Search leads…"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        <NotificationBell
          enabled={notificationsEnabled}
          onToggle={onNotificationsToggle}
        />
        <button className="refresh-btn" onClick={onRefresh} disabled={loading}>
          {loading ? '⟳' : '↻'} {loading ? 'Loading' : 'Refresh'}
        </button>
      </div>
    </header>
  )
}
