import { useState, useEffect } from 'react'
import type { Lead } from '../types'

const API = 'http://127.0.0.1:8787'

interface Props {
  lead: Lead
  onClose: () => void
  onStatusChange: (status: string) => void
  onBookmark: () => void
  onNotesChange: (notes: string) => void
}

interface Scripts {
  soft: { label: string; text: string }
  direct: { label: string; text: string }
  casual: { label: string; text: string }
}

const STATUS_OPTIONS = ['new', 'reviewing', 'contacted', 'booked', 'follow_up', 'saved', 'bad_match', 'dismissed']
const VALUE_OPTIONS = [
  { value: 'small', label: 'Small tattoo (~$150)' },
  { value: 'half_day', label: 'Half day (~$500)' },
  { value: 'full_day', label: 'Full day (~$1,000)' },
  { value: 'sleeve_project', label: 'Sleeve/project (~$3,000)' },
]

export function LeadDrawer({ lead, onClose, onStatusChange, onBookmark, onNotesChange }: Props) {
  const [notes, setNotes] = useState(lead.operator_notes || '')
  const [notesSaved, setNotesSaved] = useState(false)
  const [scripts, setScripts] = useState<Scripts | null>(null)
  const [scriptsOpen, setScriptsOpen] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)
  const [bookedValue, setBookedValue] = useState(lead.booked_value || '')
  const [customAmount, setCustomAmount] = useState('')

  useEffect(() => {
    setNotes(lead.operator_notes || '')
    setBookedValue(lead.booked_value || '')
    setScripts(null)
    setScriptsOpen(false)
  }, [lead.id])

  const saveNotes = () => {
    onNotesChange(notes)
    setNotesSaved(true)
    setTimeout(() => setNotesSaved(false), 1500)
  }

  const loadScripts = async () => {
    if (scripts) { setScriptsOpen(!scriptsOpen); return }
    try {
      const res = await fetch(`${API}/leads/${lead.id}/scripts`)
      const data = await res.json()
      setScripts(data)
      setScriptsOpen(true)
    } catch {}
  }

  const copyScript = (text: string, key: string) => {
    navigator.clipboard.writeText(text)
    setCopied(key)
    setTimeout(() => setCopied(null), 1500)
  }

  const saveBookedValue = async (val: string) => {
    setBookedValue(val)
    try {
      await fetch(`${API}/leads/${lead.id}/booked-value`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: val }),
      })
    } catch {}
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

      {/* Contact Scripts */}
      <div className="drawer__section">
        <button className="drawer__scripts-btn" onClick={loadScripts}>
          {scriptsOpen ? '▾' : '▸'} Contact Scripts
        </button>
        {scriptsOpen && scripts && (
          <div className="scripts-panel">
            {(['soft', 'direct', 'casual'] as const).map(key => (
              <div key={key} className="script-card">
                <div className="script-card__header">
                  <span className="script-card__label">{scripts[key].label}</span>
                  <button className="script-card__copy" onClick={() => copyScript(scripts[key].text, key)}>
                    {copied === key ? '✓' : '📋'}
                  </button>
                </div>
                <p className="script-card__text">{scripts[key].text}</p>
              </div>
            ))}
          </div>
        )}
      </div>

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

      {/* Booked Value */}
      {(lead.lead_status === 'booked' || bookedValue) && (
        <div className="drawer__section">
          <div className="drawer__label">Booked Value</div>
          <div className="booked-value-options">
            {VALUE_OPTIONS.map(opt => (
              <button
                key={opt.value}
                className={`booked-value-btn ${bookedValue === opt.value ? 'booked-value-btn--active' : ''}`}
                onClick={() => saveBookedValue(opt.value)}
              >
                {opt.label}
              </button>
            ))}
            <div className="booked-value-custom">
              <input
                type="number"
                placeholder="Custom $"
                value={customAmount}
                onChange={(e) => setCustomAmount(e.target.value)}
                className="booked-value-input"
              />
              <button
                className="booked-value-btn"
                onClick={() => { if (customAmount) saveBookedValue(`custom:${customAmount}`) }}
                disabled={!customAmount}
              >
                Set
              </button>
            </div>
          </div>
        </div>
      )}

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
