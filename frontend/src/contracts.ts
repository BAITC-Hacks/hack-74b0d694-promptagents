// Контракт v1.0.0. Зеркало backend/app/models.py; изменения согласовать с №1.
export interface RecommendRequest {
  city: string;
  date: string;
  event_format: string;
  category: string;
  budget_kzt: number;
  duration_hours?: number | null;
  language?: string | null;
}

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type ExplanationMode = 'baseline' | 'prepared';
export interface Evidence {
  source: 'profile' | 'description' | 'prepared';
  field: string;
  value: JsonValue;
  quote?: string | null;
}
export interface Card {
  id: string;
  name: string;
  category: string;
  city: string;
  price_from_kzt: number;
  explanation: string;
  evidence: Evidence[];
  synthetic: boolean;
  city_imputed: boolean;
  price_imputed: boolean;
  origin: 'source_original' | 'source_synthetic' | 'team_synthetic';
}
export interface AlternativeDate {
  date: string;
  card: Card;
  explanation_mode: ExplanationMode;
  warnings: string[];
}
export interface Diagnostics {
  filters: {
    reason: 'busy' | 'budget' | 'format' | 'language' | 'duration';
    excluded_count: number;
    remaining_count: number;
  }[];
  busy_profiles: { id: string; name: string; date: string; evidence: Evidence }[];
  warnings: string[];
}
export interface RecommendResponse {
  status: 'matched' | 'category_absent' | 'no_match';
  message: string;
  normalized_request: RecommendRequest;
  total_candidates: number;
  eligible_count: number;
  cards: Card[];
  alternative?: AlternativeDate | null;
  diagnostics: Diagnostics;
  explanation_mode: ExplanationMode;
  data_version: string;
}
export interface OptionsResponse {
  cities: string[];
  categories: string[];
  event_formats: string[];
  languages: string[];
  categories_by_city: { city: string; categories: string[] }[];
  date_range: { min: string; max: string };
  data_version: string;
}
export interface DataIssue {
  line?: number | null;
  id?: string | null;
  field?: string | null;
  message: string;
}
export interface ErrorResponse {
  error: {
    code: 'validation_error' | 'dataset_missing' | 'dataset_invalid' | 'not_implemented';
    message: string;
    issues: DataIssue[];
  };
}
export interface HealthResponse {
  status: 'ok' | 'degraded';
  contract_version: string;
  dataset_status: 'ready' | 'missing' | 'invalid';
  profile_count: number;
  data_version: string | null;
  recommendation_implemented: boolean;
  issues: DataIssue[];
}
