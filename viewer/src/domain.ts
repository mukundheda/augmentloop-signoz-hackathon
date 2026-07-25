export interface Decision {
  junction: string;
  stage_index: number;
  chosen: string;
  true_fastest: string;
  correct: boolean;
  travel_time_min: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  response_id: string;
}

export interface Driver {
  id: string;
  model: string;
  color: string;
  decisions: Decision[];
}

export interface Outcome {
  driver: string;
  on_time: boolean;
  graded_response_id: string;
}

export interface RaceTotals {
  decisions: number;
  correct: number;
  total_cost_usd: number;
  outcomes: number;
  cost_per_correct_usd: number | null;
}

export interface RaceRun {
  schema_version: 1;
  generated_from: string;
  drivers: Driver[];
  outcomes: Outcome[];
  totals: RaceTotals;
}

export interface RouteProperties {
  kind: string;
  junction?: string;
  route?: string;
  travel_time_min?: number;
  is_fastest?: boolean;
  stage_index?: number;
  label?: string;
  name?: string;
}

export interface GeoFeature {
  type: "Feature";
  geometry: { type: string; coordinates: unknown };
  properties: RouteProperties;
}

export interface FeatureCollection {
  type: "FeatureCollection";
  metadata?: Record<string, unknown>;
  features: GeoFeature[];
}
