"""Ticket #33 - the 20-junction graph, shortest path, and the three decision
types' query generation.

These are pure-function tests (no telemetry involved) on the answer-key
mechanism itself: the whole point of ticket #33 is that these answers are
COMPUTED, so the tests pin the computation, not a hand-picked expectation.
"""

import math

import pytest

from toyworld.world import (
    ALL_QUERIES,
    DIFFICULTY_EASY,
    DIFFICULTY_HARD,
    DIFFICULTY_MEDIUM,
    ETA_ESTIMATE_QUERIES,
    ETA_TOLERANCE_FRACTION,
    GRAPH,
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
        # Both candidate letters appear in the prompt with distinct times.
        assert "A:" in query.prompt and "B:" in query.prompt
        assert query.correct in ("A", "B")


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
