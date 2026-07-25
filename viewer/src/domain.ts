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
  observability: AgentObservability;
}

export type ObservabilityMode = "signoz" | "replay";
export type SpanStatus = "unset" | "ok" | "error";
export type EvidenceSource = "signoz" | "replay";
export type AttributeValue = string | number | boolean;

export interface AgentSpan {
  span_id: string;
  parent_span_id?: string;
  trace_id?: string;
  name: string;
  service_name: string;
  start_time_unix_nano: string;
  duration_ms: number;
  status: SpanStatus;
  source: EvidenceSource;
  attributes: Record<string, AttributeValue>;
  linked_span_ids: string[];
}

export interface AgentLog {
  timestamp_unix_nano: string;
  severity: "TRACE" | "DEBUG" | "INFO" | "WARN" | "ERROR" | "FATAL";
  body: string;
  source: EvidenceSource;
  trace_id?: string;
  span_id?: string;
  attributes: Record<string, AttributeValue>;
}

export interface SigNozLinks {
  trace?: string;
  logs?: string;
  dashboard?: string;
  traceSearch?: string;
}

export interface AgentObservability {
  mode: ObservabilityMode;
  response_id: string;
  service_name: string;
  trace_id?: string;
  evaluation_span_id?: string;
  synchronized_at?: string;
  spans: AgentSpan[];
  logs: AgentLog[];
  links?: SigNozLinks;
}

export interface SigNozConfig {
  signoz_origin: string | null;
  dashboard_path: string | null;
  service_names: string[];
}

export type CoverageState =
  | { kind: "connected"; matched: number; total: number }
  | { kind: "partial"; matched: number; total: number }
  | { kind: "offline"; matched: 0; total: number };

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
  schema_version: 3;
  generated_from: string;
  agents: AgentDecision[];
  outcomes: DeferredOutcome[];
  totals: RaceTotals;
  observability_coverage?: CoverageState;
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
