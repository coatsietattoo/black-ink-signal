import type { Filters } from '../types'

interface Props {
  stats: { total: number; hot: number; strong: number; watchlist: number }
  filters: Filters
  onFiltersChange: (f: Filters) => void
  view: 'feed' | 'admin'
  onViewChange: (v: 'feed' | 'admin') => void
}

const SCORE_BANDS = [
  { label: 'All', value: 0 },
  { label: 'Watchlist+', value: 40 },
  { label: 'Strong+', value: 60 },
  { label: 'Hot', value: 80 },
]

const STATUS_OPTIONS = [
  { label: 'All', value: null },
  { label: 'New', value: 'new' },
  { label: 'Reviewing', value: 'reviewing' },
  { label: 'Contacted', value: 'contacted' },
  { label: 'Booked', value: 'booked' },
  { label: 'Follow Up', value: 'follow_up' },
  { label: 'Saved', value: 'saved' },
  { label: 'Bad Match', value: 'bad_match' },
  { label: 'Dismissed', value: 'dismissed' },
]

export function Sidebar({ stats, filters, onFiltersChange, view, onViewChange }: Props) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand__icon">◆</span> Black Ink Signal
      </div>

      <div className="view-toggle">
        <button
          className={`view-btn ${view === 'feed' ? 'view-btn--active' : ''}`}
          onClick={() => onViewChange('feed')}
        >
          📡 Feed
        </button>
        <button
          className={`view-btn ${view === 'admin' ? 'view-btn--active' : ''}`}
          onClick={() => onViewChange('admin')}
        >
          ⚙️ Admin
        </button>
      </div>

      {view === 'feed' && (
        <>
          <div className="stats-panel">
            <div className="stat">
              <span className="stat__value">{stats.total}</span>
              <span className="stat__label">total</span>
            </div>
            <div className="stat stat--hot">
              <span className="stat__value">{stats.hot}</span>
              <span className="stat__label">hot</span>
            </div>
            <div className="stat stat--strong">
              <span className="stat__value">{stats.strong}</span>
              <span className="stat__label">strong</span>
            </div>
            <div className="stat stat--watch">
              <span className="stat__value">{stats.watchlist}</span>
              <span className="stat__label">watch</span>
            </div>
          </div>

          <div className="filter-group">
            <div className="filter-group__title">Score</div>
            <div className="filter-chips">
              {SCORE_BANDS.map(b => (
                <button
                  key={b.value}
                  className={`filter-chip ${filters.minScore === b.value ? 'filter-chip--active' : ''}`}
                  onClick={() => onFiltersChange({ ...filters, minScore: b.value })}
                >
                  {b.label}
                </button>
              ))}
            </div>
          </div>

          <div className="filter-group">
            <div className="filter-group__title">Status</div>
            <div className="filter-chips filter-chips--wrap">
              {STATUS_OPTIONS.map(s => (
                <button
                  key={s.label}
                  className={`filter-chip ${filters.status === s.value ? 'filter-chip--active' : ''}`}
                  onClick={() => onFiltersChange({ ...filters, status: s.value })}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div className="filter-group">
            <label className="filter-toggle">
              <input
                type="checkbox"
                checked={filters.bookmarkedOnly}
                onChange={() => onFiltersChange({ ...filters, bookmarkedOnly: !filters.bookmarkedOnly })}
              />
              Bookmarked only
            </label>
          </div>
        </>
      )}

      <div className="sidebar__footer">
        <div className="sidebar__scope">Public-only · Reddit · Manual review</div>
      </div>
    </aside>
  )
}
