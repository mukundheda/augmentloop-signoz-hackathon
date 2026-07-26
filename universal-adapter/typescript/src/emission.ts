/**
 * Emission of the final grade as a standard OpenTelemetry event.
 *
 * This deliberately reuses the shape proven by conformance/ts-emitter/emit.ts:
 * a flat attribute map is the language-neutral event the conformance checker
 * consumes, and the same map is converted to OTLP/HTTP JSON KeyValue form for
 * the collector. That file is a script with side effects at import time, so the
 * two small functions are mirrored here rather than imported, and the shape is
 * kept identical on purpose. If one changes, both must.
 *
 * The event stays a standard gen_ai.evaluation.result with Gradebook's two
 * extension attributes. The adapter protocol adds a way to COLLECT evidence; it
 * does not add a second telemetry contract.
 */

import type { GradedEvaluation } from "./evaluation.ts";
import type { DecisionEvidenceBundle } from "./models.ts";

export const EVENT_NAME = "gen_ai.evaluation.result";

export type AttributeValue = string | number;

export interface EvaluationEvent {
  name: typeof EVENT_NAME;
  attributes: Record<string, AttributeValue>;
}

export interface EmissionInput {
  bundle: DecisionEvidenceBundle;
  /**
   * Only a GRADED result can be emitted. An ungraded evaluation has no verdict
   * to report, and the type system refuses it here rather than letting an
   * "unknown" become a zero score in a dashboard.
   */
  result: GradedEvaluation;
  /** Omitted when unknown. It is never emitted as 0. */
  costUsd?: number;
  /** Correlation key; falls back to the bundle's correlation block. */
  providerResponseId?: string;
}

export function buildEvaluationEvent(input: EmissionInput): EvaluationEvent {
  const { bundle, result } = input;
  const attributes: Record<string, AttributeValue> = {
    "gen_ai.evaluation.name": bundle.decision.evaluation_name,
    // 1.0 / 0.0 and correct / incorrect, the encoding the frozen field table
    // requires for a machine-authoritative grade.
    "gen_ai.evaluation.score.value": result.correct ? 1.0 : 0.0,
    "gen_ai.evaluation.score.label": result.correct ? "correct" : "incorrect",
    "augmentloop.grade.source": result.authority,
    "augmentloop.grade.reason": result.reason,
    "augmentloop.decision.type": bundle.decision.decision_type,
  };

  const responseId = input.providerResponseId ?? bundle.correlation?.provider_response_id ?? undefined;
  if (responseId) attributes["gen_ai.response.id"] = responseId;

  const model = bundle.subject.model;
  if (model) attributes["gen_ai.request.model"] = model;

  // Cost is attached only when it is known. An unknown cost is an absent
  // attribute, never a zero, or every uninstrumented run would look free.
  if (typeof input.costUsd === "number" && Number.isFinite(input.costUsd) && input.costUsd >= 0) {
    attributes["augmentloop.cost.usd"] = input.costUsd;
  }

  return { name: EVENT_NAME, attributes };
}

/** Flat attribute map to OTLP/HTTP JSON KeyValue list. Mirrors emit.ts. */
export function toOtlpAttributes(
  attributes: Record<string, AttributeValue>,
): { key: string; value: { stringValue: string } | { intValue: number } | { doubleValue: number } }[] {
  return Object.entries(attributes).map(([key, value]) => ({
    key,
    value:
      typeof value === "number"
        ? Number.isInteger(value)
          ? { intValue: value }
          : { doubleValue: value }
        : { stringValue: value },
  }));
}

export interface OtlpOptions {
  serviceName?: string;
  scopeName?: string;
  traceId?: string;
  spanId?: string;
  /** Milliseconds since the epoch; defaults to now. */
  timestampMs?: number;
}

export function randomHex(bytes: number): string {
  return [...crypto.getRandomValues(new Uint8Array(bytes))]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** The OTLP/HTTP JSON body the collector already accepts. Mirrors emit.ts. */
export function buildOtlpTracePayload(event: EvaluationEvent, options: OtlpOptions = {}): unknown {
  const nanos = String((options.timestampMs ?? Date.now()) * 1_000_000);
  return {
    resourceSpans: [
      {
        resource: {
          attributes: toOtlpAttributes({ "service.name": options.serviceName ?? "gradebook-universal-adapter" }),
        },
        scopeSpans: [
          {
            scope: { name: options.scopeName ?? "gradebook-universal-adapter" },
            spans: [
              {
                traceId: options.traceId ?? randomHex(16),
                spanId: options.spanId ?? randomHex(8),
                name: event.name,
                kind: 1,
                startTimeUnixNano: nanos,
                endTimeUnixNano: nanos,
                attributes: toOtlpAttributes(event.attributes),
              },
            ],
          },
        ],
      },
    ],
  };
}

/**
 * POST one event to an OTLP/HTTP endpoint. Kept as an explicit call rather than
 * a side effect of building the event, so an adapter can produce evidence and
 * events in a process that never talks to a collector.
 */
export async function postOtlpTrace(
  event: EvaluationEvent,
  endpoint: string,
  options: OtlpOptions = {},
): Promise<void> {
  const response = await fetch(`${endpoint}/v1/traces`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildOtlpTracePayload(event, options)),
  });
  if (!response.ok) {
    throw new Error(`OTLP export failed: ${response.status} ${await response.text()}`);
  }
}

/** The canonical single-line JSON the conformance checker reads on stdin. */
export function toConformanceJson(event: EvaluationEvent): string {
  return JSON.stringify(event);
}
