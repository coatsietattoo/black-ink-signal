import type { ScoreBreakdown } from '../types'

interface Props {
  breakdown: ScoreBreakdown
}

const FACTOR_META: Record<string, { label: string; icon: string }> = {
  base_intent: { label: 'Intent signal', icon: '🎯' },
  geo_bonus: { label: 'Location match', icon: '📍' },
  project_bonus: { label: 'Project size', icon: '🖼' },
  urgency_bonus: { label: 'Urgency', icon: '⚡' },
  coverup_bonus: { label: 'Coverup signal', icon: '🔄' },
  memorial_bonus: { label: 'Memorial signal', icon: '🕊' },
  engagement_bonus: { label: 'Community engagement', icon: '💬' },
  recency_bonus: { label: 'Recency', icon: '🕐' },
  collector_bonus: { label: 'Repeat collector', icon: '📚' },
  penalty: { label: 'Noise penalty', icon: '⚠️' },
}

export function ScoreExplainer({ breakdown }: Props) {
  const factors = Object.entries(FACTOR_META)
    .map(([key, meta]) => {
      const value = breakdown[key as keyof ScoreBreakdown] as number
      return { key, ...meta, value }
    })
    .filter(f => f.value !== 0)

  return (
    <div className="score-explainer">
      <div className="score-explainer__title">Score Breakdown</div>
      <div className="score-explainer__total">
        <span>Total</span>
        <span className="score-explainer__total-value">{breakdown.total}</span>
      </div>
      <div className="score-explainer__factors">
        {factors.map(f => (
          <div key={f.key} className={`score-factor ${f.key === 'penalty' ? 'score-factor--negative' : ''}`}>
            <span className="score-factor__icon">{f.icon}</span>
            <span className="score-factor__label">{f.label}</span>
            <span className="score-factor__value">
              {f.key === 'penalty' ? `−${f.value}` : `+${f.value}`}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
