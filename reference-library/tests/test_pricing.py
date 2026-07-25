"""Roster refresh regression guard (ticket #9).

`replay` re-prices whatever recording it is given from PRICES at run time, and a
slug missing from the table fails the run rather than skipping a row. So retired
roster slugs must keep pricing successfully even after DEFAULT_ROSTER moves on.
The current roster slugs must price successfully too, or a live run fails loud
before any call is even placed.

The committed recording is now toy-world/recordings/replay-v2.jsonl, and neither
it nor replay-v1.jsonl references the retired slugs below any more. They are
guarded here for older local recordings, not for anything in this repo.
"""

from gradebook.pricing import PRICES, price

# Retired slugs, no longer present in any committed recording. These stay in
# PRICES so an older local recording still prices rather than failing the run.
OLD_REPLAY_SLUGS = (
    "anthropic/claude-3.5-haiku",
    "anthropic/claude-sonnet-4",
    "google/gemini-2.0-flash",
)

# The current roster (ticket #9 refresh): Claude Haiku 4.5, Claude Sonnet 4.6,
# Gemini 2.5 Flash Lite.
CURRENT_ROSTER_SLUGS = (
    "anthropic/claude-haiku-4.5",
    "anthropic/claude-sonnet-4.6",
    "google/gemini-2.5-flash-lite",
)


def test_old_replay_slugs_still_price_successfully():
    for model in OLD_REPLAY_SLUGS:
        assert model in PRICES, f"{model} must stay in PRICES for the committed replay"
        assert price(model, 1000, 1000) > 0


def test_current_roster_slugs_price_successfully():
    for model in CURRENT_ROSTER_SLUGS:
        assert model in PRICES, f"{model} must be priced before a live run can use it"
        assert price(model, 1000, 1000) > 0


def test_old_and_current_slugs_all_coexist_in_the_table():
    # Refreshing the roster must never shrink the table - only ever add to it.
    for model in OLD_REPLAY_SLUGS + CURRENT_ROSTER_SLUGS:
        assert model in PRICES
