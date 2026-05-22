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
  score_ups: number | null
  num_comments: number | null
  score_band: string
}

export interface Filters {
  minScore: number
  status: string | null
  bookmarkedOnly: boolean
  search: string
}
