/**
 * Decision identity (design decision D4).
 *
 * A decision_id is optional on the wire. When it is absent the consumer derives
 * it deterministically from the bundle's immutable identity fields, so replaying
 * the same bundle produces the same id and therefore the same grade rather than
 * a second one. When it is supplied it is used exactly as given, and WHICH of
 * the two happened is recorded, because "this id came from the adapter" and
 * "this id is a function of the content" are different trust statements.
 *
 * DERIVATION (the Python side must match this exactly):
 *   id = "decision-" + first 32 hex characters of
 *        sha256( canonicalize({
 *          "agent_id":        subject.agent_id        or null,
 *          "chosen":          decision.chosen         (the whole tagged value),
 *          "decision_type":   decision.decision_type,
 *          "evaluation_name": decision.evaluation_name,
 *          "harness":         subject.harness,
 *          "run_id":          subject.run_id,
 *          "session_id":      subject.session_id      or null,
 *          "task_id":         correlation.task_id     or null
 *        }) )
 *
 * The set is deliberately the fields that cannot change without the decision
 * being a DIFFERENT decision. Mutable or observational fields (model, evidence,
 * usage_refs, metadata, trace and span ids, harness_version) are excluded: a
 * bundle re-sent with one more piece of evidence attached is the same decision.
 *
 * See canonical.ts for the exact serialization.
 */

import { canonicalDigest, canonicalize, sha256Hex } from "./canonical.ts";
import type { DecisionEvidenceBundle } from "./models.ts";

export type DecisionIdSource = "adapter_supplied" | "derived";

export interface DecisionIdentity {
  decisionId: string;
  source: DecisionIdSource;
  /**
   * Digest over the bundle with decision.decision_id removed. Two bundles that
   * share an id must share this digest; if they do not, one of them is lying
   * about being the same decision.
   */
  contentDigest: string;
}

export function deriveDecisionId(bundle: DecisionEvidenceBundle): string {
  // `chosen` is in the identity set DELIBERATELY. Do not remove it to match an
  // older reading of ADR 0004, which called it mutable; it is not. What the
  // agent chose is fixed at the moment of the decision, unlike evidence and
  // usage, which keep arriving afterwards and are therefore excluded.
  //
  // Excluding it would also break a requirement of issue #101 outright: two
  // attempts at the same task in one run would derive the SAME id, the second
  // would be rejected as a conflicting duplicate, and the failed attempt would
  // disappear from the cost-per-correct numerator that the issue explicitly
  // requires it to stay in. The ADR has been amended to match this.
  const identityFields = {
    agent_id: bundle.subject.agent_id ?? null,
    chosen: bundle.decision.chosen,
    decision_type: bundle.decision.decision_type,
    evaluation_name: bundle.decision.evaluation_name,
    harness: bundle.subject.harness,
    run_id: bundle.subject.run_id,
    session_id: bundle.subject.session_id ?? null,
    task_id: bundle.correlation?.task_id ?? null,
  };
  return "decision-" + sha256Hex(canonicalize(identityFields)).slice(0, 32);
}

export function contentDigest(bundle: DecisionEvidenceBundle): string {
  const { decision, ...rest } = bundle;
  const { decision_id: _ignored, ...decisionWithoutId } = decision;
  return canonicalDigest({ ...rest, decision: decisionWithoutId });
}

export function decisionIdentity(bundle: DecisionEvidenceBundle): DecisionIdentity {
  const supplied = bundle.decision.decision_id;
  return {
    decisionId: supplied ?? deriveDecisionId(bundle),
    source: supplied ? "adapter_supplied" : "derived",
    contentDigest: contentDigest(bundle),
  };
}

export type RegistrationResult =
  | { accepted: true; status: "new" | "replay"; identity: DecisionIdentity }
  | {
      accepted: false;
      status: "conflict";
      identity: DecisionIdentity;
      /** The digest already recorded under this id. */
      existingContentDigest: string;
      message: string;
    };

/**
 * Tracks decisions seen so far in one ingest, which is what makes replay
 * idempotent and duplicate-with-different-content a rejection rather than a
 * silent overwrite. Deliberately in-memory and explicit: persistence is the
 * host application's problem, and hiding it here would make the rule invisible.
 */
export class DecisionRegistry {
  readonly #seen = new Map<string, DecisionIdentity>();

  register(bundle: DecisionEvidenceBundle): RegistrationResult {
    const identity = decisionIdentity(bundle);
    const existing = this.#seen.get(identity.decisionId);
    if (!existing) {
      this.#seen.set(identity.decisionId, identity);
      return { accepted: true, status: "new", identity };
    }
    if (existing.contentDigest === identity.contentDigest) {
      return { accepted: true, status: "replay", identity };
    }
    return {
      accepted: false,
      status: "conflict",
      identity,
      existingContentDigest: existing.contentDigest,
      message:
        `decision_id ${JSON.stringify(identity.decisionId)} was already recorded with a different content digest ` +
        `(${existing.contentDigest} vs ${identity.contentDigest}); two different decisions cannot share one id`,
    };
  }

  has(decisionId: string): boolean {
    return this.#seen.has(decisionId);
  }

  get size(): number {
    return this.#seen.size;
  }
}
