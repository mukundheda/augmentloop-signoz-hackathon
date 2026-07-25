"""The toy world (ticket #33): a 20-junction weighted graph where every
answer is computable, feeding three decision types of genuinely different
difficulty.

One decision type cannot demonstrate the product's central claim - route each
decision type to the cheapest model that is still good enough at it - because
there is nothing to compare. This module gives the toy world a real graph (20
junctions, weighted directed edges) and three decision types built on top of
the SAME graph and the SAME shortest-path routine, so every answer key is
computed, never hand-authored (spec ticket #33):

- **route_choice** (hard): pick which of two candidate routes between a start
  and destination junction, several hops apart, is fastest. Both candidates
  are real paths through the graph (the true shortest path, and the best
  alternative that diverges from its first hop); the correct answer is
  whichever has the lower total time.
- **eta_estimate** (medium): estimate the travel time, in minutes, of the
  fastest route between a start and destination junction. Graded within
  `ETA_TOLERANCE_FRACTION` of the true shortest-path time - a numeric
  tolerance, not an exact match.
- **next_hop** (easy): at one junction, choose the single cheapest outgoing
  edge. A one-step decision - the same shape the toy world had before this
  ticket, now one of three.

Difficulty is tagged per decision from the branching factor of its starting
junction (`difficulty_tier`) - more outgoing edges to compare is a harder
decision - and emitted as an attribute so correct-rate can be broken down by
difficulty, independent of decision type.
"""

from __future__ import annotations

import heapq
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

# The numeric tolerance for eta_estimate grading (acceptance criterion:
# "the numeric tolerance stated in code and docs" - also documented in
# toy-world/README.md). A model's minute estimate is graded correct when it
# falls within this fraction of the true shortest-path time.
ETA_TOLERANCE_FRACTION = 0.15

# The three decision types this world runs, named rather than inlined so the
# routing table (routing.py) and the emitted `augmentloop.decision.type`
# attribute can never drift apart - the same discipline live.py's old
# DECISION_TYPE constant existed for, extended to three types.
DECISION_TYPE_ROUTE_CHOICE = "route_choice"
DECISION_TYPE_ETA_ESTIMATE = "eta_estimate"
DECISION_TYPE_NEXT_HOP = "next_hop"
DECISION_TYPES: tuple[str, ...] = (
    DECISION_TYPE_ROUTE_CHOICE,
    DECISION_TYPE_ETA_ESTIMATE,
    DECISION_TYPE_NEXT_HOP,
)

DIFFICULTY_EASY = "easy"
DIFFICULTY_MEDIUM = "medium"
DIFFICULTY_HARD = "hard"


@dataclass(frozen=True)
class Edge:
    """One directed, weighted road out of a junction."""

    to: str
    minutes: float


@dataclass(frozen=True)
class JunctionNode:
    """One junction's fixed layout: its outgoing edges and their travel times."""

    name: str
    edges: tuple[Edge, ...]

    @property
    def branching_factor(self) -> int:
        """How many routes are on offer here - the input to difficulty tiering."""
        return len(self.edges)

    @property
    def cheapest_edge(self) -> Edge:
        """The provably-correct `next_hop` answer: the lowest-weight edge.

        Ties break by destination name for stability (mirrors the old
        `Junction.true_fastest` tie-break).
        """
        return min(self.edges, key=lambda e: (e.minutes, e.to))


def difficulty_tier(branching_factor: int) -> str:
    """Map a branching factor to a difficulty tier (spec ticket #33).

    More outgoing edges to compare is a harder decision: 2 -> easy, 3 ->
    medium, 4+ -> hard. A pure function of the graph's own shape - nothing
    hand-tuned per decision.
    """
    if branching_factor <= 2:
        return DIFFICULTY_EASY
    if branching_factor == 3:
        return DIFFICULTY_MEDIUM
    return DIFFICULTY_HARD


# The canonical 20-junction graph (spec ticket #33: "twenty junctions with
# weighted edges, so the correct answer is a shortest-path computation rather
# than a lookup"). Five layers of four junctions (J1-J4 .. J17-J20) flowing
# forward, plus lateral edges among the last layer so every one of the 20
# junctions has at least two outgoing edges (every junction can host a
# next_hop decision). Branching factors (2/3/4) are spread across every layer
# so all three difficulty tiers exist throughout the graph, not stacked at one
# end. Edge weights are minutes; every junction's own edges have distinct
# weights so `cheapest_edge` never needs a real tie-break.
GRAPH: dict[str, JunctionNode] = {
    node.name: node
    for node in (
        JunctionNode("J1", (Edge("J5", 4.0), Edge("J6", 6.0))),
        JunctionNode("J2", (Edge("J5", 5.0), Edge("J6", 3.0), Edge("J7", 7.0))),
        JunctionNode(
            "J3",
            (Edge("J6", 4.5), Edge("J7", 5.5), Edge("J8", 6.5), Edge("J5", 8.0)),
        ),
        JunctionNode("J4", (Edge("J7", 3.5), Edge("J8", 4.5))),
        JunctionNode("J5", (Edge("J9", 3.0), Edge("J10", 5.0))),
        JunctionNode("J6", (Edge("J9", 4.0), Edge("J10", 2.5), Edge("J11", 6.0))),
        JunctionNode(
            "J7",
            (Edge("J10", 3.5), Edge("J11", 4.5), Edge("J12", 5.5), Edge("J9", 7.5)),
        ),
        JunctionNode("J8", (Edge("J11", 3.0), Edge("J12", 4.0))),
        JunctionNode("J9", (Edge("J13", 4.0), Edge("J14", 6.0))),
        JunctionNode("J10", (Edge("J13", 3.0), Edge("J14", 5.0), Edge("J15", 7.0))),
        JunctionNode(
            "J11",
            (Edge("J14", 4.5), Edge("J15", 5.5), Edge("J16", 6.5), Edge("J13", 8.5)),
        ),
        JunctionNode("J12", (Edge("J15", 3.5), Edge("J16", 4.5))),
        JunctionNode("J13", (Edge("J17", 4.0), Edge("J18", 6.0))),
        JunctionNode("J14", (Edge("J17", 5.0), Edge("J18", 3.0), Edge("J19", 7.0))),
        JunctionNode(
            "J15",
            (Edge("J18", 4.5), Edge("J19", 5.5), Edge("J20", 6.5), Edge("J17", 8.5)),
        ),
        JunctionNode("J16", (Edge("J19", 3.5), Edge("J20", 4.5))),
        JunctionNode("J17", (Edge("J18", 2.0), Edge("J19", 5.0))),
        JunctionNode("J18", (Edge("J19", 2.5), Edge("J20", 4.0))),
        JunctionNode("J19", (Edge("J20", 2.0), Edge("J17", 6.0))),
        JunctionNode("J20", (Edge("J17", 3.0), Edge("J18", 5.0))),
    )
}

assert len(GRAPH) == 20, "spec ticket #33 requires exactly twenty junctions"


class NoPathError(ValueError):
    """Raised when no path exists between two junctions in the graph."""


def shortest_path(
    graph: Mapping[str, JunctionNode], start: str, end: str
) -> tuple[list[str], float]:
    """The provably-correct route: Dijkstra's shortest path by total minutes.

    Returns the node sequence (start..end inclusive) and its total time. This
    is the one true source of the `route_choice` and `eta_estimate` answer
    keys - a computation over the graph, never a hand-authored lookup.
    """
    dist: dict[str, float] = {start: 0.0}
    prev: dict[str, str] = {}
    visited: set[str] = set()
    heap: list[tuple[float, str]] = [(0.0, start)]

    while heap:
        d, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        if node == end:
            break
        for edge in graph[node].edges:
            nd = d + edge.minutes
            if nd < dist.get(edge.to, float("inf")):
                dist[edge.to] = nd
                prev[edge.to] = node
                heapq.heappush(heap, (nd, edge.to))

    if end not in dist:
        raise NoPathError(f"no path from {start!r} to {end!r}")

    path = [end]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return path, dist[end]


def second_best_path(
    graph: Mapping[str, JunctionNode], start: str, end: str
) -> Optional[tuple[list[str], float]]:
    """A real, different route from `start` to `end`: the best path that does
    NOT take the true shortest path's first hop.

    Removing the shortest path's first edge and re-running Dijkstra guarantees
    a genuinely different route (diverges from the first hop) rather than an
    arbitrary or hand-picked alternative - still a computation over the graph.
    Returns None when no such alternative exists (the first hop is the only
    way out of `start`, or the reduced graph is disconnected from `end`).
    """
    best_path, _ = shortest_path(graph, start, end)
    if len(best_path) < 2:
        return None
    first_hop_target = best_path[1]

    reduced: dict[str, JunctionNode] = dict(graph)
    origin = reduced[start]
    remaining = tuple(e for e in origin.edges if e.to != first_hop_target)
    if len(remaining) == len(origin.edges):
        return None  # nothing to remove (shouldn't happen given >=2 edges everywhere)
    reduced[start] = JunctionNode(start, remaining)

    try:
        return shortest_path(reduced, start, end)
    except NoPathError:
        return None


@dataclass(frozen=True)
class Query:
    """One decision the toy world asks a model to make.

    Carries everything live mode and the recorder need: the prompt to send,
    how to parse the reply, the computed correct answer, and how to compare
    the two - so `openrouter.py`/`direct.py` stay decision-type-agnostic (they
    just send `prompt` and call `parse`), matching the DECISION_TYPE discipline
    of never hardcoding a decision's shape in more than one place.
    """

    decision_type: str
    difficulty: str
    eval_name: str
    query_id: str
    prompt: str
    correct: Any
    checker: Callable[[Any, Any], bool]
    parse: Callable[[str], Any]
    explain: Callable[[Any], str]


def _first_number(text: str) -> float:
    """Pull the first number out of a short reply. Unparseable text becomes
    NaN, which never satisfies the tolerance check (Section: "a bad answer is
    data, not an error" - grading records it as wrong rather than crashing).
    """
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else float("nan")


def _first_token_in(text: str, options: Any) -> str:
    """Pull the first offered option out of a short reply, matching the old
    `parse_route`'s robustness: prefer an exact offered value found in the
    text, else fall back to the raw first token so a bad reply is recorded as
    a (wrong) choice, not a crash.
    """
    stripped = text.strip()
    for option in options:
        if option in stripped:
            return option
    return stripped.split()[0] if stripped.split() else stripped


def within_eta_tolerance(chosen: float, correct: float) -> bool:
    """eta_estimate's machine check: within `ETA_TOLERANCE_FRACTION` of the
    true shortest-path time. NaN (unparseable replies) is never within
    tolerance."""
    if chosen != chosen:  # NaN check without importing math
        return False
    return abs(chosen - correct) <= ETA_TOLERANCE_FRACTION * correct


def _next_hop_query(name: str) -> Query:
    node = GRAPH[name]
    edge = node.cheapest_edge
    offered = ", ".join(f"{e.to} ({e.minutes} min)" for e in node.edges)
    neighbors = tuple(e.to for e in node.edges)
    prompt = (
        f"You are at junction {name}. The roads out are: {offered}. "
        f"Reply with ONLY the name of the junction you would go to next to "
        f"minimize travel time, nothing else."
    )
    return Query(
        decision_type=DECISION_TYPE_NEXT_HOP,
        difficulty=difficulty_tier(node.branching_factor),
        eval_name="route.next_hop",
        query_id=f"next_hop-{name}",
        prompt=prompt,
        correct=edge.to,
        checker=lambda chosen, correct: chosen == correct,
        parse=lambda text: _first_token_in(text, neighbors),
        explain=lambda chosen: f"chose {chosen}; cheapest next hop is {edge.to} ({edge.minutes}m)",
    )


def _route_pairs(count: int) -> list[tuple[str, str]]:
    """Deterministic (start, end) junction pairs spanning 2/3/4-hop routes,
    filtered to pairs where a genuine second-best alternative exists (so the
    route_choice/eta_estimate questions are a real decision, not a forced
    single option). Purely a scan over the fixed GRAPH - no pair is hand-picked
    for its outcome.
    """
    starts = ["J1", "J2", "J3", "J4"]
    layer2 = ["J9", "J10", "J11", "J12"]
    layer3 = ["J13", "J14", "J15", "J16"]
    layer4 = ["J17", "J18", "J19", "J20"]

    candidates = (
        [(s, e) for s in starts for e in layer2]
        + [(s, e) for s in starts for e in layer3]
        + [(s, e) for s in starts for e in layer4]
    )

    pairs: list[tuple[str, str]] = []
    for start, end in candidates:
        try:
            _, best_time = shortest_path(GRAPH, start, end)
        except NoPathError:
            continue  # not every start reaches every candidate end
        alt = second_best_path(GRAPH, start, end)
        if alt is None:
            continue
        _, alt_time = alt
        if alt_time > best_time:  # a genuine, non-tied second option
            pairs.append((start, end))
        if len(pairs) == count:
            break

    if len(pairs) < count:
        raise NoPathError(
            f"only found {len(pairs)} route pairs with a genuine alternative; "
            f"need {count} - widen the candidate scan or adjust GRAPH weights"
        )
    return pairs


def _route_choice_query(start: str, end: str) -> Query:
    best_path, best_time = shortest_path(GRAPH, start, end)
    alt = second_best_path(GRAPH, start, end)
    assert alt is not None  # guaranteed by _route_pairs' filter
    alt_path, alt_time = alt

    # Label order comes from sorting the path tuples themselves, not from
    # which one is faster - so the letter never leaks the correct answer.
    candidates = sorted([(best_path, best_time), (alt_path, alt_time)])
    labels = "AB"
    options = {labels[i]: time for i, (_, time) in enumerate(candidates)}
    paths_by_label = {labels[i]: path for i, (path, _) in enumerate(candidates)}
    correct_label = min(options, key=lambda label: options[label])

    offered = ", ".join(
        f"{label}: {' -> '.join(paths_by_label[label])} ({options[label]} min)"
        for label in labels
    )
    prompt = (
        f"Two candidate routes from {start} to {end}: {offered}. "
        f"Reply with ONLY the single letter of the fastest route, nothing else."
    )
    difficulty = difficulty_tier(GRAPH[start].branching_factor)
    return Query(
        decision_type=DECISION_TYPE_ROUTE_CHOICE,
        difficulty=difficulty,
        eval_name="route.fastest",
        query_id=f"route_choice-{start}-{end}",
        prompt=prompt,
        correct=correct_label,
        checker=lambda chosen, correct: chosen == correct,
        parse=lambda text: _first_token_in(text, labels),
        explain=lambda chosen: (
            f"chose {chosen} ({options.get(chosen, '?')}m); "
            f"true fastest {correct_label} ({options[correct_label]}m)"
        ),
    )


def _eta_estimate_query(start: str, end: str) -> Query:
    _, best_time = shortest_path(GRAPH, start, end)
    prompt = (
        f"Estimate the travel time in minutes for the fastest route from "
        f"{start} to {end}. Reply with ONLY the number of minutes, nothing else."
    )
    difficulty = difficulty_tier(GRAPH[start].branching_factor)
    return Query(
        decision_type=DECISION_TYPE_ETA_ESTIMATE,
        difficulty=difficulty,
        eval_name="route.eta",
        query_id=f"eta_estimate-{start}-{end}",
        prompt=prompt,
        correct=best_time,
        checker=within_eta_tolerance,
        parse=_first_number,
        explain=lambda chosen: (
            f"estimated {chosen}m; true fastest time is {best_time}m "
            f"(tolerance +/-{ETA_TOLERANCE_FRACTION:.0%})"
        ),
    )


# Twenty queries per decision type (spec ticket #33: "roughly 180 decisions
# behind a single run" = 3 decision types x 3 roster models x 20 queries).
_ROUTE_PAIRS = _route_pairs(20)

NEXT_HOP_QUERIES: tuple[Query, ...] = tuple(_next_hop_query(name) for name in sorted(GRAPH))
ROUTE_CHOICE_QUERIES: tuple[Query, ...] = tuple(
    _route_choice_query(s, e) for s, e in _ROUTE_PAIRS
)
ETA_ESTIMATE_QUERIES: tuple[Query, ...] = tuple(
    _eta_estimate_query(s, e) for s, e in _ROUTE_PAIRS
)

ALL_QUERIES: tuple[Query, ...] = (
    ROUTE_CHOICE_QUERIES + ETA_ESTIMATE_QUERIES + NEXT_HOP_QUERIES
)

assert len(ALL_QUERIES) == 60, "spec ticket #33: 20 queries per decision type"

# Looked up by the recorder/replay (recorder.py, replay.py) to recompute a
# query's correct answer, checker, and difficulty fresh from this module
# rather than trusting a stored value in a recording file - the answer key
# stays computed, never a frozen copy that could drift from the graph.
QUERIES_BY_ID: dict[str, Query] = {q.query_id: q for q in ALL_QUERIES}
