export interface Lead {
  id: number
  source: string
  source_item_id: string
  canonical_url: string | null
  author_handle: string | null
  title: string | null
  body: string | null
  subreddit: string | null
  created_at: string | null
  fetched_at: string
  lead_score: number
  lead_status: string
  geo_estimate: string | null
  geo_confidence: string | null
  keyword_trigger: string | null
  semantic_label: string | null
  booking_likelihood: number | null
  project_size: string | null
  tone: string | null
  urgency: string | null
  style_interest: string | null
  outreach_angle: string | null
  intent_summary: string | null
  bookmarked: boolean
  hidden: boolean
  operator_notes: string | null
  booked_value: string | null
  score_ups: number | null
  num_comments: number | null
  score_band: string
  score_breakdown: ScoreBreakdown | null
}

export interface ScoreBreakdown {
  base_intent: number
  geo_bonus: number
  project_bonus: number
  urgency_bonus: number
  engagement_bonus: number
  recency_bonus: number
  collector_bonus: number
  coverup_bonus: number
  memorial_bonus: number
  penalty: number
  total: number
  keyword_trigger: string
  semantic_label: string
  geo_estimate: string
  geo_confidence: string
}

export interface Filters {
  minScore: number
  status: string | null
  bookmarkedOnly: boolean
  search: string
}

export interface AppPrefs {
  compactMode: boolean
  view: 'feed' | 'admin'
  filters: Filters
  selectedLeadId: number | null
  soundEnabled: boolean
}
