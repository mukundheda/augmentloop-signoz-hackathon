"""Ticket #33 - the 20-junction graph, shortest path, and the three decision
types' query generation.

These are pure-function tests (no telemetry involved) on the answer-key
mechanism itself: the whole point of ticket #33 is that these answers are
COMPUTED, so the tests pin the computation, not a hand-picked expectation.
"""

import math
import re

import pytest

from toyworld.world import (
    ALL_QUERIES,
    DIFFICULTY_EASY,
    DIFFICULTY_HARD,
    DIFFICULTY_MEDIUM,
    ETA_ESTIMATE_QUERIES,
    ETA_TOLERANCE_FRACTION,
    GRAPH,
    MAP_TEXT,
    NEXT_HOP_QUERIES,
    QUERIES_BY_ID,
    ROUTE_CHOICE_QUERIES,
    difficulty_tier,
    second_best_path,
    shortest_path,
    within_eta_tolerance,
)


def test_graph_has_twenty_junctions():
    assert len(GRAPH) == 20


def test_every_junction_has_at_least_two_edges():
    """Every junction must host a next_hop decision (spec: twenty junctions)."""
    for name, node in GRAPH.items():
        assert node.branching_factor >= 2, f"{name} has too few edges to be a decision"


def test_shortest_path_is_the_true_minimum_by_brute_force():
    """Cross-check Dijkstra against exhaustive enumeration for one pair."""

    def all_paths(start, end, max_hops=6):
        found = []

        def dfs(node, path, time):
            if len(path) - 1 > max_hops:
                return
            if node == end and len(path) > 1:
                found.append(time)
                return
            for edge in GRAPH[node].edges:
                if edge.to in path:
                    continue
                dfs(edge.to, path + [edge.to], time + edge.minutes)

        dfs(start, [start], 0.0)
        return found

    path, time = shortest_path(GRAPH, "J1", "J17")
    assert path[0] == "J1"
    assert path[-1] == "J17"
    assert time == pytest.approx(min(all_paths("J1", "J17")))


def test_shortest_path_raises_when_unreachable():
    from toyworld.world import NoPathError

    with pytest.raises(NoPathError):
        shortest_path(GRAPH, "J20", "J1")  # forward-flowing graph, no path back to J1


def test_second_best_path_diverges_from_the_first_hop():
    best_path, best_time = shortest_path(GRAPH, "J1", "J9")
    alt = second_best_path(GRAPH, "J1", "J9")
    assert alt is not None
    alt_path, alt_time = alt
    assert alt_path[1] != best_path[1]  # genuinely different first hop
    assert alt_time >= best_time  # Dijkstra's result is the global optimum


@pytest.mark.parametrize(
    "branching_factor,expected",
    [(2, DIFFICULTY_EASY), (3, DIFFICULTY_MEDIUM), (4, DIFFICULTY_HARD), (5, DIFFICULTY_HARD)],
)
def test_difficulty_tier_from_branching_factor(branching_factor, expected):
    assert difficulty_tier(branching_factor) == expected


def test_within_eta_tolerance_accepts_the_stated_fraction():
    correct = 20.0
    assert within_eta_tolerance(correct * (1 + ETA_TOLERANCE_FRACTION), correct)
    assert within_eta_tolerance(correct * (1 - ETA_TOLERANCE_FRACTION), correct)


def test_within_eta_tolerance_rejects_outside_the_stated_fraction():
    correct = 20.0
    assert not within_eta_tolerance(correct * (1 + ETA_TOLERANCE_FRACTION) + 1, correct)


def test_within_eta_tolerance_rejects_unparseable_nan():
    assert not within_eta_tolerance(math.nan, 20.0)


def test_twenty_queries_per_decision_type():
    assert len(NEXT_HOP_QUERIES) == 20
    assert len(ROUTE_CHOICE_QUERIES) == 20
    assert len(ETA_ESTIMATE_QUERIES) == 20
    assert len(ALL_QUERIES) == 60


def test_next_hop_correct_answer_is_the_cheapest_edge():
    for query in NEXT_HOP_QUERIES:
        junction_name = query.query_id.removeprefix("next_hop-")
        node = GRAPH[junction_name]
        assert query.correct == node.cheapest_edge.to
        assert query.decision_type == "next_hop"


def test_route_choice_offers_two_genuinely_different_candidates():
    for query in ROUTE_CHOICE_QUERIES:
        assert query.decision_type == "route_choice"
        # Both candidate letters appear in the prompt (their times do not -
        # see test_no_prompt_hands_the_model_a_precomputed_answer).
        assert "A:" in query.prompt and "B:" in query.prompt
        assert query.correct in ("A", "B")


def test_eta_parse_reads_a_bare_numeric_reply():
    parse = ETA_ESTIMATE_QUERIES[0].parse
    assert parse("17.0") == 17.0
    assert parse("21.5") == 21.5
    assert parse("7") == 7.0


def test_eta_parse_ignores_junction_ids_and_takes_the_final_answer():
    """The real claude-sonnet-4.6 reply shape that exposed the parser bug.

    Scored on its FIRST number this reply grades as 1.0 (the `1` inside `J1`)
    against a true answer of 7.0 - marking a correct answer wrong. Both
    failure modes are pinned here: junction ids are not quantities, and the
    answer is the last number, not the first.
    """
    reply = (
        "I need to find the fastest route from J1 to J9.\n\n"
        "Let me use Dijkstra's algorithm.\n\n"
        "Starting from J1, initial distances:\n- J1: 0\n\n"
        "From J1: J5=4.0, J6=6.0\n\nProcess J5 (4.0):\n- J9 = 4.0+3.0 = 7.0\n\n"
        "The fastest route is J1 -> J5 -> J9, taking 7.0 minutes."
    )
    assert ETA_ESTIMATE_QUERIES[0].parse(reply) == 7.0


def test_eta_parse_returns_nan_when_there_is_no_number_at_all():
    """A reply naming only junctions has no quantity in it - NaN, graded
    wrong, never a crash ("a bad answer is data, not an error")."""
    assert math.isnan(ETA_ESTIMATE_QUERIES[0].parse("J1 -> J5 -> J9"))
    assert math.isnan(ETA_ESTIMATE_QUERIES[0].parse("I cannot answer that."))


def test_every_prompt_carries_the_whole_map_exactly_once():
    """No decision type gets a privileged or partial view of the world."""
    for query in ALL_QUERIES:
        assert query.prompt.count(MAP_TEXT) == 1, query.query_id


def test_no_prompt_hands_the_model_a_precomputed_answer():
    """The regression guard for the defect this test file's queries once had.

    Every prompt used to ship the arithmetic already done: route_choice
    printed each candidate's total time ("A: J1 -> J5 -> J9 (7.0 min)") and
    next_hop printed every outgoing edge's time beside the edge. Both
    collapsed to "pick the smaller number in front of you", every model in
    the roster scored identically, and the whole right-sizing claim - route
    each decision type to the cheapest model still good enough at it - had
    nothing to stand on, because no decision separated any two models.

    So: travel times may appear ONLY inside the shared map. Once the map is
    removed, no decimal number may remain anywhere in the question body.
    (Junction names like J1 are integers-after-a-letter and survive this;
    edge weights like 4.0 are what it catches.)
    """
    for query in ALL_QUERIES:
        body = query.prompt.replace(MAP_TEXT, "")
        leaked = re.findall(r"\d+\.\d+", body)
        assert not leaked, f"{query.query_id} leaks precomputed values: {leaked}"


def test_eta_estimate_correct_answer_matches_shortest_path_time():
    for query in ETA_ESTIMATE_QUERIES:
        start, end = query.query_id.removeprefix("eta_estimate-").split("-", 1)
        _, true_time = shortest_path(GRAPH, start, end)
        assert query.correct == pytest.approx(true_time)
        assert query.decision_type == "eta_estimate"


def test_all_difficulty_tiers_present_across_decision_types():
    tiers = {q.difficulty for q in ALL_QUERIES}
    assert tiers == {DIFFICULTY_EASY, DIFFICULTY_MEDIUM, DIFFICULTY_HARD}


def test_queries_by_id_is_a_complete_reverse_index():
    assert len(QUERIES_BY_ID) == len(ALL_QUERIES)
    for query in ALL_QUERIES:
        assert QUERIES_BY_ID[query.query_id] is query


def test_next_hop_parse_recovers_the_reply():
    query = NEXT_HOP_QUERIES[0]
    junction_name = query.query_id.removeprefix("next_hop-")
    neighbor = GRAPH[junction_name].edges[0].to
    assert query.parse(f"I'll go to {neighbor}.") == neighbor


def test_route_choice_parse_recovers_the_letter():
    query = ROUTE_CHOICE_QUERIES[0]
    assert query.parse("The answer is A.") == "A"
    assert query.parse("B") == "B"


def test_eta_estimate_parse_recovers_a_number():
    query = ETA_ESTIMATE_QUERIES[0]
    assert query.parse("about 12.5 minutes") == 12.5
    assert math.isnan(query.parse("no idea"))
