/**
 * TypeScript half of the cross-language parity runner.
 *
 * Do not run this by hand to answer a parity question. Run:
 *
 *     python universal-adapter/parity/run.py
 *
 * This program answers questions; it never judges the answers. It loads the
 * shared inputs (the fixture corpus and the case files in parity/cases/), asks
 * the TypeScript implementation what it makes of each one, and writes a flat map
 * of "group/key" -> "answer as a string" to stdout as JSON. probe.py answers the
 * same questions from the Python implementation, and run.py diffs the two maps.
 *
 * The two probes must stay structurally identical. If one of them ever starts
 * asking a question the other does not, run.py reports the key as missing rather
 * than quietly comparing fewer things than the README claims.
 *
 * Zero npm dependencies and no build step: Node 22+ executes this file and the
 * .ts sources it imports directly, which is the same claim the package itself
 * makes and would be embarrassing for its own parity runner to break.
 *
 * Usage: node probe.ts [path-to-pricing-table.json]
 * The pricing table argument carries Python's live gradebook.pricing table
 * across the language boundary. Without it the pricing answers are reported as
 * "unavailable:no_table_supplied" rather than skipped silently.
 */

import { readFileSync, existsSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { canonicalize } from "../typescript/src/canonical.ts";
import { deriveDecisionId, contentDigest } from "../typescript/src/identity.ts";
import { validate } from "../typescript/src/validation.ts";
import { pricingTableId } from "../typescript/src/costing.ts";
import type { DecisionEvidenceBundle, PricingTable } from "../typescript/src/models.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const ADAPTER_ROOT = resolve(HERE, "..");
const FIXTURES = join(ADAPTER_ROOT, "fixtures");
const CASES = join(HERE, "cases");

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8"));
}

/** The answer to every question is a string, including "it threw". */
function attempt(fn: () => string): string {
  try {
    return fn();
  } catch (error) {
    const name = error instanceof Error ? error.constructor.name : typeof error;
    return `error:${name}`;
  }
}

/**
 * Expand the $parity escapes the case files use for unspellable inputs. JSON has
 * no NaN, no infinities, and no comfortable way to write a 513 character string,
 * so the case files spell those as tagged objects and both probes expand them
 * identically before anything is measured.
 */
function decodeEscapes(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(decodeEscapes);
  if (value !== null && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const tag = record["$parity"];
    if (typeof tag === "string" && Object.keys(record).length <= 3) {
      if (tag === "nan") return Number.NaN;
      if (tag === "inf") return Number.POSITIVE_INFINITY;
      if (tag === "-inf") return Number.NEGATIVE_INFINITY;
      if (tag === "repeat") return String(record["char"]).repeat(Number(record["count"]));
      throw new Error(`unknown $parity escape ${JSON.stringify(tag)}`);
    }
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(record)) out[key] = decodeEscapes(item);
    return out;
  }
  return value;
}

/** The JSON type name, which both languages must agree a document has. */
function jsonType(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  switch (typeof value) {
    case "boolean":
      return "boolean";
    case "number":
      return "number";
    case "string":
      return "string";
    case "object":
      return "object";
    default:
      return `unrepresentable:${typeof value}`;
  }
}

interface CorpusCase {
  file: string;
  schema?: string;
  expect: "valid" | "invalid" | "not_validated";
  container?: "single" | "array";
}

/** A case is one document, or every element of one, as the index declares. */
function documents(testCase: CorpusCase, parsed: unknown): unknown[] {
  if (testCase.container === "array") {
    return Array.isArray(parsed) ? [...parsed] : [];
  }
  return [parsed];
}

function main(): void {
  const answers: Record<string, Record<string, string>> = {
    canonical: {},
    canonical_fixture: {},
    validation_corpus: {},
    validation_extra: {},
    decision_id: {},
    content_digest: {},
    pricing: {},
  };

  // 1. Canonical serialization over the adversarial value set.
  const canonicalCases = (readJson(join(CASES, "canonical.json")) as { cases: { id: string; value: unknown }[] }).cases;
  for (const testCase of canonicalCases) {
    const value = decodeEscapes(testCase.value);
    answers["canonical"]![testCase.id] = attempt(() => canonicalize(value));
  }

  // 2. The shared fixture corpus: validation verdicts, and the canonical form of
  //    every document in it.
  const index = readJson(join(FIXTURES, "index.json")) as { cases: CorpusCase[] };
  for (const testCase of index.cases) {
    const name = testCase.file;
    const path = join(FIXTURES, name);
    if (!existsSync(path)) {
      answers["validation_corpus"]![name] = "error:MissingFixture";
      continue;
    }
    const parsed = readJson(path);
    const docs = documents(testCase, parsed);

    if (testCase.expect === "not_validated") {
      // Raw harness input. Validating it against a protocol schema would be a
      // category error, so the only shared observation available is that both
      // languages parse it into the same shape.
      answers["validation_corpus"]![name] = `not_validated:${jsonType(parsed)}`;
    } else if (testCase.container === "array" && !Array.isArray(parsed)) {
      answers["validation_corpus"]![name] = "error:NotAnArray";
      continue;
    } else {
      docs.forEach((document, position) => {
        answers["validation_corpus"]![`${name}#${position}`] = attempt(() =>
          validate(testCase.schema ?? "", document).length === 0 ? "accepted" : "rejected",
        );
      });
    }

    docs.forEach((document, position) => {
      answers["canonical_fixture"]![`${name}#${position}`] = attempt(() => canonicalize(document));
    });

    // 3. Derived decision ids, for every VALID bundle document in the corpus.
    if (testCase.schema === "decision-evidence-bundle" && testCase.expect === "valid") {
      docs.forEach((document, position) => {
        const key = `${name}#${position}`;
        answers["decision_id"]![key] = attempt(() => deriveDecisionId(document as DecisionEvidenceBundle));
        answers["content_digest"]![key] = attempt(() => contentDigest(document as DecisionEvidenceBundle));
      });
    }
  }

  // 4. Extra validation inputs, at the type-system edges the corpus does not reach.
  const recordCases = (readJson(join(CASES, "records.json")) as { cases: { id: string; kind: string; record: unknown }[] })
    .cases;
  for (const testCase of recordCases) {
    const record = decodeEscapes(testCase.record);
    answers["validation_extra"]![testCase.id] = attempt(() =>
      validate(testCase.kind, record).length === 0 ? "accepted" : "rejected",
    );
  }

  // 5. The pricing table id. The table itself lives in Python's gradebook.pricing
  //    and cannot be imported here, so run.py exports it from probe.py and hands
  //    it over as a file. What is compared is the id the two implementations
  //    derive from the same table.
  const tablePath = process.argv[2];
  if (!tablePath) {
    answers["pricing"]!["pricing_table_id"] = "unavailable:no_table_supplied";
    answers["pricing"]!["pricing_table_canonical"] = "unavailable:no_table_supplied";
    answers["pricing"]!["pricing_table_model_count"] = "unavailable:no_table_supplied";
  } else {
    const table = readJson(tablePath) as PricingTable;
    answers["pricing"]!["pricing_table_id"] = attempt(() => pricingTableId(table));
    answers["pricing"]!["pricing_table_canonical"] = attempt(() => canonicalize(table));
    answers["pricing"]!["pricing_table_model_count"] = String(Object.keys(table.models ?? {}).length);
  }

  process.stdout.write(JSON.stringify({ implementation: "typescript", answers }));
}

main();
