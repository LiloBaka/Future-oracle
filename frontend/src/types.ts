export type Location = {
  id: number
  name: string
  country_code: string | null
  latitude: number
  longitude: number
  timezone: string
  is_active: boolean
}

export type Factor = {
  code: string
  label: string
  raw_value: number | null
  normalized_value: number
  base_weight: number
  effective_weight: number
  contribution: number
  details: Record<string, unknown> | null
}

export type SourceMetric = {
  source_code: string
  raw_record_id: number
  normalized_metric_id: number
  fetched_at: string
  precipitation_probability_pct: number | null
  rain_amount_mm: number | null
  humidity_pct: number | null
  cloud_cover_pct: number | null
  pressure_hpa: number | null
  temperature_c: number | null
  wind_speed_kmh: number | null
  rain_hours: number | null
  completeness: number
}

export type Evaluation = {
  status: 'pending' | 'correct' | 'incorrect'
  actual_rain: boolean | null
  actual_rain_mm: number | null
  absolute_probability_error: number | null
  brier_score: number | null
  evaluated_at: string | null
  error_message: string | null
}

export type Prediction = {
  id: number
  location: Location
  target_date: string
  rain_probability_pct: number
  prediction_class: 'rain' | 'no_rain'
  confidence_pct: number
  risk_score: number
  risk_level: 'low' | 'medium' | 'high'
  decision_threshold_pct: number
  algorithm_version: string
  explanation: string
  created_at: string
  factors: Factor[]
  sources: SourceMetric[]
  evaluation: Evaluation | null
}
