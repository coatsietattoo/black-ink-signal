import type { Lead } from '../types'

const BAND_COLORS: Record<string, string> = {
  hot: '#ef4444',
  strong: '#f59e0b',
  watchlist: '#3b82f6',
  low: '#6b7280',
}

const STATUS_OPTIONS = ['new', 'reviewing', 'contacted', 'booked', 'follow_up', 'saved', 'bad_match', 'dismissed']

function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

interface Props {
  lead: Lead
  isSelected: boolean
  onSelect: () => void
  onStatusChange: (status: string) => void
  onBookmark: () => void
}

export function LeadCard({ lead, isSelected, onSelect, onStatusChange, onBookmark }: Props) {
  const bandColor = BAND_COLORS[lead.score_band] || '#6b7280'

  return (
    <div
      className={`lead-card ${isSelected ? 'lead-card--selected' : ''}`}
      onClick={onSelect}
      style={{ borderLeftColor: bandColor }}
    >
      <div className="lead-card__top">
        <span className="lead-score" style={{ background: bandColor }}>
          {lead.lead_score}
        </span>
        <span className="lead-band">{lead.score_band}</span>
        <span className="lead-source">r/{lead.subreddit || lead.source}</span>
        {lead.geo_estimate && (
          <span className="lead-geo">📍 {lead.geo_estimate}</span>
        )}
        <span className="lead-time">{timeAgo(lead.created_at)}</span>
        <button
          className={`lead-bookmark ${lead.bookmarked ? 'lead-bookmark--active' : ''}`}
          onClick={(e) => { e.stopPropagation(); onBookmark() }}
          title={lead.bookmarked ? 'Remove bookmark' : 'Bookmark'}
        >
          {lead.bookmarked ? '★' : '☆'}
        </button>
      </div>

      <div className="lead-card__title">{lead.title || '(no title)'}</div>

      {lead.body && (
        <div className="lead-card__preview">
          {lead.body.length > 180 ? lead.body.slice(0, 180) + '…' : lead.body}
        </div>
      )}

      <div className="lead-card__meta">
        {lead.keyword_trigger && (
          <span className="lead-tag lead-tag--keyword">{lead.keyword_trigger.split(';')[0].trim()}</span>
        )}
        {lead.semantic_label && (
          <span className="lead-tag lead-tag--intent">{lead.semantic_label.replace(/_/g, ' ')}</span>
        )}
        <span className={`lead-tag lead-tag--status lead-tag--status-${lead.lead_status}`}>
          {lead.lead_status}
        </span>
      </div>

      <div className="lead-card__actions">
        {STATUS_OPTIONS.filter(s => s !== lead.lead_status).slice(0, 3).map(s => (
          <button
            key={s}
            className={`action-btn action-btn--${s}`}
            onClick={(e) => { e.stopPropagation(); onStatusChange(s) }}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}
