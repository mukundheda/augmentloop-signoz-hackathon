export type DecisionType = "route_choice" | "eta_estimate" | "next_hop";
export type Difficulty = "easy" | "medium" | "hard";
export type Coordinate = [number, number];

export interface AgentDecision {
  agent_id: string;
  response_id: string;
  model: string;
  color: string;
  decision_type: DecisionType;
  difficulty: Difficulty;
  query_id: string;
  start: string;
  destination: string;
  chosen: string | number;
  correct_answer: string | number;
  is_correct: boolean;
  chosen_path: string[];
  correct_path: string[];
  chosen_polyline: Coordinate[];
  correct_polyline: Coordinate[];
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  outcome: DeferredOutcome | null;
}

export interface DeferredOutcome {
  graded_response_id: string;
  on_time: boolean;
  model: string;
}

export interface RaceTotals {
  decisions: number;
  correct: number;
  total_cost_usd: number;
  outcomes: number;
  cost_per_correct_usd: number | null;
  by_type: Record<DecisionType, number>;
  by_model: Record<string, number>;
}

export interface RaceRun {
  schema_version: 2;
  generated_from: string;
  agents: AgentDecision[];
  outcomes: DeferredOutcome[];
  totals: RaceTotals;
}

export interface MapFeature {
  type: "Feature";
  properties: {
    kind: "road" | "building" | "landmark" | "water" | "green";
    name?: string;
    highway?: string;
    width?: number;
    height?: number;
    levels?: number;
  };
  geometry: {
    type: "LineString" | "Polygon" | "Point";
    coordinates: unknown;
  };
}

export interface PuneMap {
  type: "FeatureCollection";
  metadata: Record<string, unknown>;
  features: MapFeature[];
}

export interface RoadMapping {
  schema_version: 1;
  nodes: Record<string, { coordinate: Coordinate; osm_node_id: number; layer: number }>;
  edges: Record<string, { start: string; end: string; minutes: number; polyline: Coordinate[] }>;
  metadata: Record<string, unknown>;
}
