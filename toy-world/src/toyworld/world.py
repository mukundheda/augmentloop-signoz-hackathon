"""The toy world: a tiny road network where the truth is computable.

Three junctions; at each junction a driver picks one of the offered routes,
each with a known travel time. Because the engine knows every travel time, the
provably-fastest choice at each junction is just `min` - which is exactly what
makes every driver decision math-gradeable (spec user story 15).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JunctionDecision:
    """One driver's route choice at one junction, as replayed or recorded."""

    driver: str
    junction: str
    options: dict[str, float]  # route name -> travel time (minutes)
    chosen: str
    model: str
    input_tokens: int
    output_tokens: int
    response_id: str

    @property
    def true_fastest(self) -> str:
        """The provably-correct answer: the route with the lowest travel time.

        Ties break deterministically by route name so replay grading is stable.
        """
        return min(sorted(self.options), key=self.options.__getitem__)


@dataclass(frozen=True)
class JourneyOutcome:
    """The real-world verdict on one driver's journey, arriving after the fact.

    In replay mode this is part of the recording; in live mode it comes from
    the simulation clock. `on_time` grades whichever decision the recording
    holds responsible via `graded_response_id` - deliberately the wrong turn
    that made the driver late (e.g. driver-3's J1), not necessarily the
    journey-closing junction. Reality grades attach to causes, not to whatever
    happened last (spec user story 7).
    """

    driver: str
    on_time: bool
    graded_response_id: str  # the decision this outcome judges (span-link target)
