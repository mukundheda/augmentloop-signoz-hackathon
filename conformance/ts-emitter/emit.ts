/**
 * A second-language emitter for the Gradebook contract (ticket #44).
 *
 * ADR 0002's moat is that Gradebook extends a *cross-language* OpenTelemetry
 * standard. This TypeScript emitter proves it in a language that is not the
 * Python reference library, and deliberately with **zero npm dependencies** -
 * only Node built-ins (`fetch`, `crypto`) - so "any stack can emit the contract"
 * is demonstrated at its most minimal: no OTel SDK, just the OTLP/HTTP JSON
 * payload the collector already accepts.
 *
 * It emits one conforming `gen_ai.evaluation.result` event (a math grade) with
 * the two mandatory extension attributes, POSTs it to the SigNoz OTLP endpoint,
 * and prints the same event as the language-neutral JSON the conformance
 * checker consumes.
 *
 * Run (Node 22+, runs .ts directly; SigNoz stack up):
 *   node conformance/ts-emitter/emit.ts            # emit to SigNoz + print event
 *   node conformance/ts-emitter/emit.ts --json     # print the event JSON only
 * Pipe straight into the checker:
 *   node conformance/ts-emitter/emit.ts --json | python conformance/check_conformance.py -
 */

const ENDPOINT = process.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? "http://localhost:4318";
const JSON_ONLY = process.argv.includes("--json");

// The canonical, language-neutral event the conformance checker validates.
const event = {
  name: "gen_ai.evaluation.result",
  attributes: {
    "gen_ai.evaluation.name": "quote.verbatim",
    "gen_ai.evaluation.score.value": 1.0,
    "gen_ai.evaluation.score.label": "correct",
    "gen_ai.response.id": "ts-emit-1",
    "augmentloop.grade.source": "math", // mandatory extension (ADR 0001)
    "augmentloop.cost.usd": 0.00021, // priced from token counts elsewhere
    "gen_ai.request.model": "anthropic/claude-haiku-4.5",
    "augmentloop.decision.type": "quote_extraction",
  } as Record<string, string | number>,
};

function hex(bytes: number): string {
  return [...crypto.getRandomValues(new Uint8Array(bytes))]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Convert our flat attribute map to OTLP/HTTP JSON KeyValue list. */
function toOtlpAttributes(attrs: Record<string, string | number>) {
  return Object.entries(attrs).map(([key, value]) => ({
    key,
    value:
      typeof value === "number"
        ? Number.isInteger(value)
          ? { intValue: value }
          : { doubleValue: value }
        : { stringValue: value },
  }));
}

async function emitToSigNoz(): Promise<void> {
  const now = String(Date.now() * 1_000_000); // ms -> ns
  const payload = {
    resourceSpans: [
      {
        resource: {
          attributes: toOtlpAttributes({ "service.name": "gradebook-ts" }),
        },
        scopeSpans: [
          {
            scope: { name: "gradebook-ts-emitter" },
            spans: [
              {
                traceId: hex(16),
                spanId: hex(8),
                name: event.name,
                kind: 1,
                startTimeUnixNano: now,
                endTimeUnixNano: now,
                attributes: toOtlpAttributes(event.attributes),
              },
            ],
          },
        ],
      },
    ],
  };

  const res = await fetch(`${ENDPOINT}/v1/traces`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`OTLP export failed: ${res.status} ${await res.text()}`);
  }
  process.stderr.write(
    `Emitted one conforming gen_ai.evaluation.result to ${ENDPOINT} (service gradebook-ts).\n`,
  );
}

async function main(): Promise<void> {
  if (!JSON_ONLY) {
    await emitToSigNoz();
  }
  // stdout carries only the canonical event, so it pipes cleanly to the checker.
  process.stdout.write(JSON.stringify(event) + "\n");
}

main().catch((err) => {
  process.stderr.write(String(err) + "\n");
  process.exit(1);
});
