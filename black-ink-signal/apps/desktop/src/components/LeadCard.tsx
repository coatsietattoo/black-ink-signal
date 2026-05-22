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
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

// Age factor: 0.0 (ancient) to 1.0 (fresh) — for visual fading
function ageFactor(iso: string | null): number {
  if (!iso) return 0.4
  const hours = (Date.now() - new Date(iso).getTime()) / 3600000
  if (hours < 1) return 1.0
  if (hours < 6) return 0.95
  if (hours < 24) return 0.85
  if (hours < 48) return 0.7
  if (hours < 72) return 0.55
  return 0.4
}

// Leads that have been actioned don't fade
function shouldFade(lead: Lead): boolean {
  const actioned = ['contacted', 'saved', 'booked', 'follow_up']
  return !actioned.includes(lead.lead_status) && !lead.bookmarked
}

interface Props {
  lead: Lead
  isSelected: boolean
  onSelect: () => void
  onStatusChange: (status: string) => void
  onBookmark: () => void
  isNew?: boolean
  compactMode?: boolean
}

export function LeadCard({ lead, isSelected, onSelect, onStatusChange, onBookmark, isNew, compactMode }: Props) {
  const bandColor = BAND_COLORS[lead.score_band] || '#6b7280'
  const fade = shouldFade(lead) ? ageFactor(lead.created_at) : 1.0
  const isHot = lead.score_band === 'hot'

  const cardClass = [
    'lead-card',
    isSelected && 'lead-card--selected',
    isNew && 'lead-card--new',
    isHot && 'lead-card--hot-pulse',
    compactMode && 'lead-card--compact',
  ].filter(Boolean).join(' ')

  return (
    <div
      className={cardClass}
      onClick={onSelect}
      style={{
        borderLeftColor: bandColor,
        opacity: fade < 1 ? Math.max(fade, 0.4) : undefined,
      }}
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

      {!compactMode && lead.body && (
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

      {!compactMode && (
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
      )}
    </div>
  )
}
