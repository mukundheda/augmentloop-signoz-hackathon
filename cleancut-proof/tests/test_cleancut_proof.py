"""Ticket #11 - CleanCut real-substrate proof.

No API key needed: model calls are faked at the ModelCaller seam. All
telemetry assertions use the literal frozen attribute names from
docs/conventions.md section 9.
"""

import pytest

from cleancutproof import (
    BudgetExceededError,
    ModelReply,
    filler_checker,
    lexical_fillers,
    openrouter_caller,
    quote_checker,
    replay_clip_outcomes,
    run_detections,
)

# The synthetic sample transcript contains exactly these pure-filler occurrences.
SAMPLE_FILLERS = ["um", "uh", "uh", "um", "hmm"]
VERBATIM_QUOTE = "Consistency beats\nintensity every single time."


# --- checkers ---------------------------------------------------------------


def test_lexical_ground_truth_counts_occurrences(sample_transcript):
    assert lexical_fillers(sample_transcript) == SAMPLE_FILLERS


def test_filler_checker_requires_exact_occurrences():
    truth = ["um", "uh", "uh"]
    assert filler_checker("uh um uh", truth)          # order-free
    assert not filler_checker("um uh", truth)         # missed one occurrence
    assert not filler_checker("um uh uh like", truth) # contextual word invented


def test_quote_checker_is_verbatim_substring(sample_transcript):
    assert quote_checker(VERBATIM_QUOTE, sample_transcript)
    assert quote_checker(f'"{VERBATIM_QUOTE}"', sample_transcript)  # quoted ok
    assert not quote_checker(
        "Consistency is better than intensity every time.", sample_transcript
    )  # paraphrase = provably wrong
    assert not quote_checker("", sample_transcript)


# --- detection runs ---------------------------------------------------------


def _fake_caller(answers_by_model):
    """A ModelCaller whose answers and token usage are scripted per model."""

    def call(model, prompt):
        fillers, quote, tokens = answers_by_model[model]
        text = fillers if "filler" in prompt.lower() else quote
        return ModelReply(
            text=text,
            input_tokens=tokens,
            output_tokens=20,
            response_id=f"fake-{model.split('/')[-1]}",
        )

    return call


ANSWERS = {
    # model: (filler answer, quote answer, input_tokens). Keyed by the live
    # roster slugs (runner.ROSTER); each must exist in gradebook.pricing.PRICES.
    "anthropic/claude-haiku-4.5": ("um uh uh um hmm", VERBATIM_QUOTE, 500),
    "anthropic/claude-sonnet-4.6": ("um uh uh um hmm", VERBATIM_QUOTE, 500),
    # Flash Lite misses a filler and paraphrases the quote - 0/2.
    "google/gemini-2.5-flash-lite": (
        "um uh hmm",
        "Consistency is better than intensity.",
        500,
    ),
}


def test_detections_graded_across_the_roster(proof, sample_transcript):
    provider, exporter = proof
    summary = run_detections(
        sample_transcript,
        caller=_fake_caller(ANSWERS),
        transcript_label="sample-01",
        tracer_provider=provider,
    )

    assert summary.decisions == 6  # 2 jobs x 3 models
    assert summary.correct == 4    # haiku 2/2, sonnet 2/2, flash 0/2

    events = [
        s
        for s in exporter.get_finished_spans()
        if s.name == "gen_ai.evaluation.result"
    ]
    assert len(events) == 6
    for e in events:
        assert e.attributes["augmentloop.grade.source"] == "math"
        assert e.attributes["augmentloop.cost.usd"] > 0
        assert e.attributes["augmentloop.decision.type"] in {
            "filler_detection",
            "quote_extraction",
        }

    flash = summary.by_model["google/gemini-2.5-flash-lite"]
    assert flash["decisions"] == 2 and flash["correct"] == 0
    # Cheaper model, wrong answers: cost-per-correct exposes it, raw cost hides it.
    assert flash["cost_usd"] < summary.by_model["anthropic/claude-sonnet-4.6"]["cost_usd"]


def test_response_ids_stay_non_identifying(proof, sample_transcript):
    provider, exporter = proof
    run_detections(
        sample_transcript,
        caller=_fake_caller(ANSWERS),
        transcript_label="sample-01",
        tracer_provider=provider,
    )
    for s in exporter.get_finished_spans():
        if s.name == "gen_ai.evaluation.result":
            # Label + job + fake completion id only - no transcript content.
            assert s.attributes["gen_ai.response.id"].startswith("sample-01-")


# --- clip reality replay ----------------------------------------------------


def test_clip_outcomes_reality_graded_with_span_links(
    proof, outcomes, sample_clips_csv
):
    provider, exporter = proof
    outcomes_provider, outcomes_exporter = outcomes

    summary = replay_clip_outcomes(
        sample_clips_csv,
        tracer_provider=provider,
        outcomes_provider=outcomes_provider,
    )

    # Gate 0.45 vs kept: rows 01,02,05,06 agree; 03 (published, discarded) and
    # 04 (held, kept) disagree.
    assert summary.clip_outcomes == 6
    assert summary.clip_correct == 4

    decision_spans = {
        s.name: s for s in exporter.get_finished_spans() if s.name.startswith("clip decision")
    }
    grades = outcomes_exporter.get_finished_spans()
    assert len(grades) == 6
    for g in grades:
        assert g.attributes["augmentloop.grade.source"] == "reality"
        assert g.attributes["gen_ai.evaluation.name"] == "clip.publish_worthy"
        # Unknown historical token counts -> no cost attribute, never a fake 0.
        assert "augmentloop.cost.usd" not in g.attributes
        clip_id = g.attributes["gen_ai.response.id"].removeprefix("clip-")
        target = decision_spans[f"clip decision {clip_id}"]
        assert len(g.links) == 1
        assert g.links[0].context.span_id == target.context.span_id


# --- budget cap -------------------------------------------------------------


def test_budget_cap_fails_loud_before_spending():
    caller = openrouter_caller("fake-key", budget_usd=0.0)
    with pytest.raises(BudgetExceededError):
        caller("anthropic/claude-haiku-4.5", "hi")  # no network call happens


# --- NONE sentinel (found on the real capture run, #11) ---------------------


def test_none_sentinel_stripped_wherever_it_appears():
    """gpt-4o appended NONE *after* listing fillers on the live run.

    Only stripping a whole-answer "NONE" left a stray token the multiset
    comparison counted as a filler, failing a model for how it framed its
    answer rather than for which fillers it found.
    """
    from cleancutproof.runner import _strip_none_sentinel

    truth = ["er", "uh", "uh", "uh", "uh", "uh", "um", "um"]
    # correct fillers + a trailing sentinel must PASS
    assert filler_checker(_strip_none_sentinel("er uh uh uh uh uh um um NONE"), truth)
    # whole-answer NONE still means "found nothing"
    assert _strip_none_sentinel("NONE").strip() == ""
    # a genuinely wrong count still FAILS (this is the real gpt-4o answer)
    assert not filler_checker(
        _strip_none_sentinel("er uh uh uh um uh um uh um NONE"), truth
    )


# --- performance_prediction: leak guard + recording (round 2) ---------------


def test_performance_prompt_is_clean_but_guard_catches_a_leak():
    from cleancutproof.runner import (
        PERFORMANCE_PROMPT, PromptLeakError, assert_no_performance_leak)

    t = "So today we talk about compounding. It works over time."
    # The shipped prompt must pass.
    assert_no_performance_leak(PERFORMANCE_PROMPT.format(transcript=t), t)
    # Scaffolding that hands over the answer must fail loudly, before spending.
    with pytest.raises(PromptLeakError):
        assert_no_performance_leak("This video got 13059 views. Predict.\n" + t, t)


def test_leak_guard_ignores_the_transcript_itself():
    """A creator saying "views" on camera is content, not a leak.

    Checking the transcript would reject most real material and quietly shrink
    the corpus, so only the scaffolding we wrap around it is scanned.
    """
    from cleancutproof.runner import PERFORMANCE_PROMPT, assert_no_performance_leak

    t = "I always say views do not matter and subscribers do not matter."
    assert_no_performance_leak(PERFORMANCE_PROMPT.format(transcript=t), t)


def test_recording_caller_replays_without_calling_the_model(tmp_path):
    from cleancutproof.runner import ModelReply, recording_caller

    path = tmp_path / "rec.jsonl"
    live = {"n": 0}

    def fake(model, prompt):
        live["n"] += 1
        return ModelReply(text="0.73", input_tokens=100, output_tokens=3, response_id="r1")

    rec = recording_caller(path, record_from=fake)
    first = rec("openai/gpt-4o", "predict this")
    assert live["n"] == 1

    replay = recording_caller(path)
    again = replay("openai/gpt-4o", "predict this")
    assert live["n"] == 1, "replay must make no model call, that is the point"
    assert (again.text, again.input_tokens, again.response_id) == (
        first.text, first.input_tokens, first.response_id)


def test_recording_caller_refuses_when_prompts_drift(tmp_path):
    """A silent miss would let a replay quietly grade a different question."""
    from cleancutproof.runner import ModelReply, recording_caller

    path = tmp_path / "rec.jsonl"
    rec = recording_caller(
        path,
        record_from=lambda m, p: ModelReply(text="0.5", input_tokens=1, output_tokens=1, response_id="x"),
    )
    rec("openai/gpt-4o", "prompt A")
    with pytest.raises(KeyError):
        recording_caller(path)("openai/gpt-4o", "prompt B")
