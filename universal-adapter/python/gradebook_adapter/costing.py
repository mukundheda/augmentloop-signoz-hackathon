"""Attribute cost to decisions without ever charging the same money twice.

The headline metric divides cost by verified correct decisions, so both halves
of that fraction are attack surface. This module defends the numerator.

What goes wrong in multi-agent systems, and what stops it here:

- The same model call is reported by a parent and by a child. Stopped by
  `usage_id`: two records sharing an id are the SAME consumption, charged once.
- A parent aggregate already contains its children's calls, and both get summed.
  Stopped by `contains_usage_ids` when the harness declares it, and by
  parent/child agent scope when it does not: the narrower records win, because a
  measurement of the parts is more precise than a measurement of the whole.
- A run total gets copied onto every decision in the run. Stopped by refusing to
  sum a run-scoped record with narrower records that carry a known cost, and by
  assigning a run aggregate to exactly ONE decision, the terminal one, when it is
  all we have.
- A cost nobody measured shows up as zero. Stopped everywhere: absent cost is
  `None`, and `None` is never added, never defaulted and never displayed as 0.

Cost coverage is REPORTED and never thresholded here. A library that quietly
picked a minimum coverage would be making a research judgement on behalf of its
caller. `compare_cost_per_correct` therefore takes `min_coverage` with no
default, so nobody compares two harnesses at 12 percent coverage by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

from gradebook import pricing

from .evaluation import EvaluationResult
from .models import (
    CostProvenance,
    DecisionEvidenceBundle,
    DecisionIdentity,
    OutcomeRecord,
    UsageRecord,
    UsageScope,
    canonical_json,
    resolve_decision_identity,
    sha256_hex,
)


class CostingError(Exception):
    """Base class for conditions this module refuses to guess its way past."""


class ConflictingDecisionIdError(CostingError):
    """Two different decisions arrived wearing the same id.

    Rejected rather than overwritten (ADR 0004). Two different decisions under
    one id is a corruption that gets worse the longer it goes unnoticed, so it
    fails at ingestion, where someone can still fix the adapter that produced it.
    """


class UsageContainmentCycleError(CostingError):
    """Usage records claim to contain each other.

    Left alone this would drop every record in the cycle and silently lose real
    money from the numerator, which is the failure mode this whole module exists
    to prevent.
    """


class UnpriceableUsageError(CostingError):
    """A token-estimated record names a model with no entry in the price table."""


class InsufficientCoverageError(CostingError):
    """A comparison was attempted below the caller's own coverage floor."""


# --------------------------------------------------------------------------
# Pricing table identity
# --------------------------------------------------------------------------


def compute_pricing_table_id() -> str:
    """Identity of the rates in gradebook.pricing.PRICES.

    A cost figure that cannot be traced to the exact rates that produced it is
    not reproducible, and prices drift. Computed from the live table rather than
    written down, so editing a rate changes the id automatically and an old
    figure can never be silently re-attributed to new rates.
    """
    models: dict[str, dict[str, float]] = {}
    for slug, rate in pricing.PRICES.items():
        if not slug.isascii():
            # A non-ASCII slug would be escaped by the canonical serializer, and
            # an escaping difference between two languages would produce two
            # different ids for one table. Refused rather than risked.
            raise CostingError(
                f"pricing table slug {slug!r} is not ASCII; the pricing digest "
                "is a cross-language identity and must not depend on escaping"
            )
        models[slug] = {
            "input_per_1m_usd": rate.input_per_mtok,
            "output_per_1m_usd": rate.output_per_mtok,
        }
    # No version field inside the hash on purpose: the digest IS the version, so
    # nobody has to remember to bump anything when a rate changes.
    table = {"currency": "usd", "models": models}
    return "gradebook.pricing@" + sha256_hex(canonical_json(table))[:12]


PRICING_TABLE_ID: str = compute_pricing_table_id()


# --------------------------------------------------------------------------
# The ledger
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LedgerNote:
    """Something the ledger accepted but wants the caller to know about."""

    kind: str
    subject_id: str
    detail: str


class EvidenceLedger:
    """Everything ingested for a run, deduplicated on the way in.

    Ingestion only. Nothing here evaluates anything: collection and evaluation
    are separate concerns, so adding a bundle can never have the side effect of
    running a checker or emitting telemetry.
    """

    def __init__(self) -> None:
        self._bundles: dict[str, DecisionEvidenceBundle] = {}
        self._identities: dict[str, DecisionIdentity] = {}
        self._order: list[str] = []
        self._usage: dict[str, UsageRecord] = {}
        self._outcomes: dict[str, OutcomeRecord] = {}
        self.notes: list[LedgerNote] = []

    # -- decisions --------------------------------------------------------

    def add_bundle(self, bundle: DecisionEvidenceBundle) -> DecisionIdentity:
        """Add a bundle, or recognise it as a replay of one already held.

        Replaying the same bundle is a no-op and returns the same identity, so a
        CI importer re-reading yesterday's JSONL or a wrapper re-run after a
        crash cannot inflate the decision count.
        """
        identity = resolve_decision_identity(bundle)
        existing = self._identities.get(identity.decision_id)
        if existing is None:
            self._bundles[identity.decision_id] = bundle
            self._identities[identity.decision_id] = identity
            self._order.append(identity.decision_id)
            return identity
        if existing.content_digest != identity.content_digest:
            raise ConflictingDecisionIdError(
                f"decision_id {identity.decision_id!r} was already recorded with "
                f"different content (held digest {existing.content_digest[:12]}, "
                f"incoming {identity.content_digest[:12]}). Two different "
                "decisions wearing one id is rejected rather than overwritten: "
                "if the adapter mints ids per run, it must derive them instead "
                "of inventing them."
            )
        return existing

    # -- usage ------------------------------------------------------------

    def add_usage(self, record: UsageRecord) -> None:
        """Add a usage record, charging a repeated `usage_id` only once."""
        held = self._usage.get(record.usage_id)
        if held is None:
            self._usage[record.usage_id] = record
            return
        if held.to_dict() != record.to_dict():
            # Not fatal: the schema's rule is that one id is one consumption, so
            # the first wins. It is surfaced because two adapters disagreeing
            # about the same call is worth a human look.
            self.notes.append(LedgerNote(
                kind="conflicting_usage_content",
                subject_id=record.usage_id,
                detail="a second record with this usage_id differed in content; "
                       "the first was kept and this one was not charged",
            ))

    # -- outcomes ---------------------------------------------------------

    def add_outcome(self, record: OutcomeRecord) -> bool:
        """Add an outcome. Replaying an `outcome_id` records nothing new."""
        if record.outcome_id in self._outcomes:
            return False
        self._outcomes[record.outcome_id] = record
        return True

    # -- views ------------------------------------------------------------

    @property
    def decision_ids(self) -> tuple[str, ...]:
        """Ids in ingestion order. Order decides which decision a run aggregate
        lands on, so it is preserved rather than left to dict iteration luck."""
        return tuple(self._order)

    @property
    def bundles(self) -> Mapping[str, DecisionEvidenceBundle]:
        return dict(self._bundles)

    @property
    def identities(self) -> Mapping[str, DecisionIdentity]:
        return dict(self._identities)

    @property
    def usage(self) -> tuple[UsageRecord, ...]:
        return tuple(self._usage.values())

    @property
    def outcomes(self) -> tuple[OutcomeRecord, ...]:
        return tuple(self._outcomes.values())

    def outcomes_for(self, decision_id: str) -> tuple[OutcomeRecord, ...]:
        return tuple(o for o in self._outcomes.values() if o.decision_id == decision_id)


# --------------------------------------------------------------------------
# Attribution
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ChargedUsage:
    usage_id: str
    cost_usd: Optional[float]
    provenance: CostProvenance


@dataclass(frozen=True)
class DecisionCost:
    """What one decision cost, and how much that figure can be trusted."""

    decision_id: str
    cost_usd: Optional[float]
    provenance: Optional[CostProvenance]
    usage_ids: tuple[str, ...]
    partial: bool = False

    @property
    def is_known(self) -> bool:
        return self.cost_usd is not None


@dataclass(frozen=True)
class CostCoverage:
    """How much of the graded population actually has a cost behind it."""

    graded_decisions: int
    decisions_with_cost: int

    @property
    def ratio(self) -> Optional[float]:
        # Undefined rather than 0.0 when nothing was graded. Reporting 0 percent
        # coverage for an empty population is a statement nobody made.
        if self.graded_decisions == 0:
            return None
        return self.decisions_with_cost / self.graded_decisions


@dataclass(frozen=True)
class CostReport:
    per_decision: Mapping[str, DecisionCost]
    coverage: CostCoverage
    charged_usage_ids: tuple[str, ...]
    skipped_usage: Mapping[str, str]
    unattributed_usage_ids: tuple[str, ...]
    unassigned_run_aggregates: tuple[str, ...]
    pricing_table_id: str = PRICING_TABLE_ID
    notes: tuple[LedgerNote, ...] = ()

    def cost_for(self, decision_id: str) -> Optional[float]:
        entry = self.per_decision.get(decision_id)
        return None if entry is None else entry.cost_usd


def record_cost(record: UsageRecord, *, allow_unpriceable: bool = False
                ) -> tuple[Optional[float], CostProvenance]:
    """The strongest cost figure available for ONE usage record.

    Precedence, strongest first: a provider figure wins outright, because it is
    the only source that reflects the actual contract, discounts and rounding.
    Failing that, token counts against the pricing table. Failing that, unknown,
    which stays unknown.
    """
    if record.provider_cost_usd is not None:
        return record.provider_cost_usd, CostProvenance.PROVIDER_REPORTED

    if record.cost_provenance is CostProvenance.UNKNOWN:
        return None, CostProvenance.UNKNOWN

    if (
        record.model is not None
        and record.input_tokens is not None
        and record.output_tokens is not None
    ):
        try:
            cost = pricing.price(record.model, record.input_tokens,
                                 record.output_tokens)
        except pricing.UnknownModelError:
            if not allow_unpriceable:
                # Same fail-loud reasoning as gradebook's own pricing: a silently
                # missing cost quietly corrupts the headline metric.
                raise UnpriceableUsageError(
                    f"usage {record.usage_id!r} claims "
                    f"{record.cost_provenance.value} for model {record.model!r}, "
                    "which has no entry in gradebook.pricing.PRICES. Add the rate, "
                    "or pass allow_unpriceable=True to record it as unknown cost."
                ) from None
            return None, CostProvenance.UNKNOWN
        return cost, record.cost_provenance

    # A token estimate with no tokens is not an estimate.
    return None, CostProvenance.UNKNOWN


def attribute_costs(
    ledger: EvidenceLedger,
    results: Mapping[str, EvaluationResult],
    *,
    allow_unpriceable: bool = False,
    terminal_decision_id: Optional[str] = None,
) -> CostReport:
    """Charge every usage record exactly once, across the decisions it names.

    `terminal_decision_id` is where a run-level aggregate lands when a run total
    is all the harness gave us. When it is not supplied, the LAST graded decision
    is used, on the documented convention that callers list decisions in run
    order. It is an explicit option because "terminal" is a fact about the run
    that the ledger cannot always see.
    """
    records = list(ledger.usage)
    skipped: dict[str, str] = {}

    surviving = _drop_contained(records, skipped)
    surviving = _drop_superseded_agent_aggregates(surviving, skipped)

    costs: dict[str, tuple[Optional[float], CostProvenance]] = {
        record.usage_id: record_cost(record, allow_unpriceable=allow_unpriceable)
        for record in surviving
    }
    surviving, run_only = _split_run_aggregates(surviving, costs, skipped)

    charged: dict[str, list[ChargedUsage]] = {}
    charged_ids: list[str] = []
    unattributed: list[str] = []

    for record in surviving:
        targets = [d for d in record.decision_ids if d in ledger.bundles]
        if not targets:
            # Real consumption that is not yet attributable. Kept visible rather
            # than dropped: it is exactly what makes coverage less than 1.
            unattributed.append(record.usage_id)
            continue
        cost, provenance = costs[record.usage_id]
        # Split evenly across the decisions the record names. Charging the whole
        # figure to each would double count, and there is no reported basis for
        # any other split, so the even one is the only one that invents nothing.
        share = None if cost is None else cost / len(record.decision_ids)
        for target in targets:
            charged.setdefault(target, []).append(
                ChargedUsage(record.usage_id, share, provenance)
            )
        charged_ids.append(record.usage_id)
        if len(targets) < len(record.decision_ids):
            skipped[record.usage_id] = (
                f"names {len(record.decision_ids)} decisions but only "
                f"{len(targets)} are in the ledger; the remaining shares are "
                "unattributed rather than redistributed"
            )

    unassigned: list[str] = []
    for record in run_only:
        terminal = _terminal_decision(results, terminal_decision_id)
        if terminal is None:
            # Never spread across decisions and never dropped quietly: without a
            # verified terminal decision there is nothing a run total belongs to.
            unassigned.append(record.usage_id)
            skipped[record.usage_id] = (
                "run aggregate with no terminal decision to attach to; a run "
                "total is never spread across decisions"
            )
            continue
        cost, provenance = costs[record.usage_id]
        charged.setdefault(terminal, []).append(
            ChargedUsage(record.usage_id, cost, provenance)
        )
        charged_ids.append(record.usage_id)

    per_decision = {
        decision_id: _combine(decision_id, items)
        for decision_id, items in charged.items()
    }

    graded_ids = [d for d, r in results.items() if r.graded]
    with_cost = sum(
        1 for d in graded_ids
        if d in per_decision and per_decision[d].is_known
    )
    return CostReport(
        per_decision=per_decision,
        coverage=CostCoverage(graded_decisions=len(graded_ids),
                              decisions_with_cost=with_cost),
        charged_usage_ids=tuple(charged_ids),
        skipped_usage=skipped,
        unattributed_usage_ids=tuple(unattributed),
        unassigned_run_aggregates=tuple(unassigned),
        notes=tuple(ledger.notes),
    )


def _drop_contained(records: list[UsageRecord],
                    skipped: dict[str, str]) -> list[UsageRecord]:
    """Honour `contains_usage_ids`, which removes the guesswork entirely."""
    contained: dict[str, str] = {}
    for record in records:
        for child in record.contains_usage_ids:
            contained[child] = record.usage_id
    for record in records:
        holder = contained.get(record.usage_id)
        if holder is not None and holder in contained:
            if contained[holder] == record.usage_id:
                raise UsageContainmentCycleError(
                    f"usage {record.usage_id!r} and {holder!r} each declare they "
                    "contain the other; one of the two adapters is wrong and "
                    "dropping both would silently lose real cost"
                )
    kept = []
    for record in records:
        holder = contained.get(record.usage_id)
        if holder is None:
            kept.append(record)
        else:
            skipped[record.usage_id] = (
                f"already included in usage {holder!r} via contains_usage_ids"
            )
    return kept


def _drop_superseded_agent_aggregates(records: list[UsageRecord],
                                      skipped: dict[str, str]) -> list[UsageRecord]:
    """Drop a parent agent's total when its children are reported separately.

    The narrower records win. Adding both is the classic multi-agent double
    count, and of the two, the per-call records are the more precise measurement.
    """
    children: dict[str, set[str]] = {}
    for record in records:
        if record.agent_id is not None and record.parent_agent_id is not None:
            children.setdefault(record.parent_agent_id, set()).add(record.agent_id)

    narrow_agents = {
        record.agent_id for record in records
        if record.scope in (UsageScope.MODEL_INVOCATION, UsageScope.DECISION)
        and record.agent_id is not None
    }

    kept = []
    for record in records:
        if record.scope is UsageScope.AGENT and record.agent_id is not None:
            subtree = _descendants(record.agent_id, children)
            covered = sorted(narrow_agents & subtree)
            if covered:
                skipped[record.usage_id] = (
                    "agent aggregate superseded by narrower records for "
                    + ", ".join(covered)
                )
                continue
        kept.append(record)
    return kept


def _descendants(agent_id: str, children: Mapping[str, set[str]]) -> set[str]:
    seen = {agent_id}
    stack = [agent_id]
    while stack:
        for child in children.get(stack.pop(), ()):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen


def _split_run_aggregates(records: list[UsageRecord],
                          costs: Mapping[str, tuple[Optional[float], CostProvenance]],
                          skipped: dict[str, str]
                          ) -> tuple[list[UsageRecord], list[UsageRecord]]:
    """Separate run-scoped totals, and drop the ones a run already details.

    A run-scoped record covers everything inside it, so summing it with narrower
    records from the same run counts the same money twice. The suppression turns
    on a narrower record with a KNOWN cost, not merely a narrower record: if the
    per-call records exist but none of them carries a figure, the run total is
    the only money anybody reported, and discarding it would turn a measured cost
    into no cost at all.
    """
    runs_with_detail = {
        record.run_id for record in records
        if record.scope is not UsageScope.RUN
        and costs[record.usage_id][0] is not None
    }
    narrower: list[UsageRecord] = []
    run_only: list[UsageRecord] = []
    for record in records:
        if record.scope is not UsageScope.RUN:
            narrower.append(record)
        elif record.run_id in runs_with_detail:
            skipped[record.usage_id] = (
                f"run total for {record.run_id!r} superseded by narrower records "
                "from the same run"
            )
        else:
            run_only.append(record)
    return narrower, run_only


def _terminal_decision(results: Mapping[str, EvaluationResult],
                       explicit: Optional[str]) -> Optional[str]:
    """The one decision a run aggregate is allowed to land on.

    An explicit id wins. Otherwise the last graded decision, on the convention
    that callers list decisions in run order. Never spread, never copied onto
    every decision in the run, and never assigned twice.
    """
    if explicit is not None:
        return explicit
    graded = [decision_id for decision_id, result in results.items() if result.graded]
    return graded[-1] if graded else None


def _combine(decision_id: str, items: list[ChargedUsage]) -> DecisionCost:
    known = [item for item in items if item.cost_usd is not None]
    if not known:
        return DecisionCost(
            decision_id=decision_id, cost_usd=None, provenance=None,
            usage_ids=tuple(item.usage_id for item in items),
        )
    # The weakest link decides how much the total can be trusted: a sum that is
    # part measurement and part estimate is an estimate.
    provenance = max((item.provenance for item in known), key=lambda p: p.strength)
    return DecisionCost(
        decision_id=decision_id,
        cost_usd=sum(item.cost_usd or 0.0 for item in known),
        provenance=provenance,
        usage_ids=tuple(item.usage_id for item in items),
        partial=len(known) < len(items),
    )


# --------------------------------------------------------------------------
# The headline metric
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CostPerCorrect:
    """Cost per verified correct decision, with its own caveats attached."""

    total_cost_usd: float
    correct_decisions: int
    graded_decisions: int
    coverage: CostCoverage
    decision_type: Optional[str] = None

    @property
    def value(self) -> Optional[float]:
        # No correct decisions is undefined, not infinite and not zero.
        if self.correct_decisions == 0:
            return None
        return self.total_cost_usd / self.correct_decisions


def cost_per_correct(report: CostReport, results: Mapping[str, EvaluationResult], *,
                     decision_type: Optional[str] = None) -> CostPerCorrect:
    """Total attributable cost of evaluated attempts over verified correct ones.

    Incorrect attempts stay in the numerator on purpose. A harness that gets
    there on the fifth try spent five attempts' worth of money, and a metric that
    counted only the successful attempt would reward thrashing.
    """
    graded = [
        (decision_id, result) for decision_id, result in results.items()
        if result.graded
        and (decision_type is None or result.decision_type == decision_type)
    ]
    total = 0.0
    for decision_id, _ in graded:
        entry = report.per_decision.get(decision_id)
        if entry is not None and entry.cost_usd is not None:
            total += entry.cost_usd
    # VERIFIED correct, which means math or reality authority. An ai_judge pass
    # is a real result and is not a verified correct decision, so it never grows
    # this denominator.
    correct = sum(1 for _, result in graded if result.counts_as_correct)
    with_cost = sum(
        1 for decision_id, _ in graded
        if decision_id in report.per_decision
        and report.per_decision[decision_id].is_known
    )
    return CostPerCorrect(
        total_cost_usd=total,
        correct_decisions=correct,
        graded_decisions=len(graded),
        coverage=CostCoverage(graded_decisions=len(graded),
                              decisions_with_cost=with_cost),
        decision_type=decision_type,
    )


@dataclass(frozen=True)
class Comparison:
    left: CostPerCorrect
    right: CostPerCorrect
    min_coverage: float

    @property
    def ratio(self) -> Optional[float]:
        left, right = self.left.value, self.right.value
        if left is None or right is None or right == 0:
            return None
        return left / right


def compare_cost_per_correct(left: CostPerCorrect, right: CostPerCorrect, *,
                             min_coverage: float) -> Comparison:
    """Compare two cost-per-correct figures, above an explicit coverage floor.

    `min_coverage` has no default, and that is a deliberate ergonomic obstacle.
    Comparing two harnesses whose costs are 12 percent attributed produces a
    number that looks like a result and is not one, and a default would let that
    happen without anybody choosing it. The caller states the floor their claim
    can survive.
    """
    if not 0.0 <= min_coverage <= 1.0:
        raise ValueError(f"min_coverage must be between 0 and 1, got {min_coverage}")
    for label, side in (("left", left), ("right", right)):
        ratio = side.coverage.ratio
        if ratio is None:
            raise InsufficientCoverageError(
                f"{label} side has no graded decisions, so its cost coverage is "
                "undefined and there is nothing to compare"
            )
        if ratio < min_coverage:
            raise InsufficientCoverageError(
                f"{label} side has cost coverage {ratio:.0%} "
                f"({side.coverage.decisions_with_cost} of "
                f"{side.coverage.graded_decisions} graded decisions), below the "
                f"{min_coverage:.0%} floor this comparison was asked for. Attribute "
                "more usage or lower the floor deliberately."
            )
    if left.decision_type != right.decision_type:
        raise ValueError(
            f"refusing to compare decision types {left.decision_type!r} and "
            f"{right.decision_type!r}; harnesses draw decision boundaries "
            "differently, so only like units may be compared"
        )
    return Comparison(left=left, right=right, min_coverage=min_coverage)


def usage_for_run(records: Iterable[UsageRecord], run_id: str) -> tuple[UsageRecord, ...]:
    """Small convenience for callers holding a mixed stream of runs."""
    return tuple(record for record in records if record.run_id == run_id)
