import { useState } from 'react'
import type { Lead } from '../types'

interface Props {
  lead: Lead
  onClose: () => void
  onStatusChange: (status: string) => void
  onBookmark: () => void
  onNotesChange: (notes: string) => void
}

const STATUS_OPTIONS = ['new', 'reviewing', 'contacted', 'saved', 'dismissed']

export function LeadDrawer({ lead, onClose, onStatusChange, onBookmark, onNotesChange }: Props) {
  const [notes, setNotes] = useState(lead.operator_notes || '')
  const [notesSaved, setNotesSaved] = useState(false)

  const saveNotes = () => {
    onNotesChange(notes)
    setNotesSaved(true)
    setTimeout(() => setNotesSaved(false), 1500)
  }

  return (
    <aside className="drawer">
      <div className="drawer__header">
        <h2>Lead Detail</h2>
        <button className="drawer__close" onClick={onClose}>✕</button>
      </div>

      <div className="drawer__score-row">
        <span className={`drawer__score drawer__score--${lead.score_band}`}>
          {lead.lead_score}
        </span>
        <span className="drawer__band">{lead.score_band}</span>
        <button
          className={`lead-bookmark ${lead.bookmarked ? 'lead-bookmark--active' : ''}`}
          onClick={onBookmark}
        >
          {lead.bookmarked ? '★ Saved' : '☆ Save'}
        </button>
      </div>

      <div className="drawer__section">
        <div className="drawer__label">Title</div>
        <div className="drawer__value">{lead.title || '(none)'}</div>
      </div>

      <div className="drawer__section">
        <div className="drawer__label">Full Text</div>
        <div className="drawer__body">{lead.body || '(empty)'}</div>
      </div>

      <div className="drawer__grid">
        <div><span className="drawer__label">Source</span><br/>r/{lead.subreddit || lead.source}</div>
        <div><span className="drawer__label">Author</span><br/>{lead.author_handle || '?'}</div>
        <div><span className="drawer__label">Geo</span><br/>{lead.geo_estimate || '—'} ({lead.geo_confidence})</div>
        <div><span className="drawer__label">Posted</span><br/>{lead.created_at ? new Date(lead.created_at).toLocaleString() : '?'}</div>
        <div><span className="drawer__label">Upvotes</span><br/>{lead.score_ups ?? '—'}</div>
        <div><span className="drawer__label">Comments</span><br/>{lead.num_comments ?? '—'}</div>
      </div>

      {lead.keyword_trigger && (
        <div className="drawer__section">
          <div className="drawer__label">Keyword Triggers</div>
          <div className="drawer__tags">
            {lead.keyword_trigger.split(';').map((k, i) => (
              <span key={i} className="lead-tag lead-tag--keyword">{k.trim()}</span>
            ))}
          </div>
        </div>
      )}

      {lead.semantic_label && (
        <div className="drawer__section">
          <div className="drawer__label">Intent</div>
          <span className="lead-tag lead-tag--intent">{lead.semantic_label.replace(/_/g, ' ')}</span>
        </div>
      )}

      {lead.intent_summary && (
        <div className="drawer__section">
          <div className="drawer__label">AI Summary</div>
          <div className="drawer__value">{lead.intent_summary}</div>
        </div>
      )}

      {lead.canonical_url && (
        <div className="drawer__section">
          <div className="drawer__label">Source Link</div>
          <a href={lead.canonical_url} target="_blank" rel="noopener noreferrer" className="drawer__link">
            {lead.canonical_url}
          </a>
        </div>
      )}

      <div className="drawer__section">
        <div className="drawer__label">Status</div>
        <div className="drawer__status-buttons">
          {STATUS_OPTIONS.map(s => (
            <button
              key={s}
              className={`action-btn action-btn--${s} ${lead.lead_status === s ? 'action-btn--current' : ''}`}
              onClick={() => onStatusChange(s)}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="drawer__section">
        <div className="drawer__label">Operator Notes</div>
        <textarea
          className="drawer__notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Add notes about this lead..."
          rows={4}
        />
        <button className="drawer__save-notes" onClick={saveNotes}>
          {notesSaved ? '✓ Saved' : 'Save notes'}
        </button>
      </div>
    </aside>
  )
}
