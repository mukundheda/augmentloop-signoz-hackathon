"""Ticket #43 - a reality grade needs no hand-written checker.

The whole point is that the adopter writes zero comparison logic: the app's own
signal is the verdict. These tests exercise that seam and assert on emitted
telemetry (the literal frozen attribute names), never on library internals.
"""

import json

from gradebook import RealitySignal, ref_from_ids, ref_to_ids


def _observe_under_span(sig, tracer_provider, key, response_id):
    """Simulate the decision happening inside a model-call span, then observe it."""
    tracer = tracer_provider.get_tracer("test-harness")
    with tracer.start_as_current_span("chat model") as span:
        sig.observe(key, response_id=response_id)
        return span.get_span_context()


def test_on_outcome_records_reality_grade_with_no_checker(tracer_provider, exporter):
    sig = RealitySignal(
        "clip.kept", decision_type="clip_scoring", tracer_provider=tracer_provider
    )

    # An ordinary existing handler whose return value is already the verdict -
    # no comparison against a ground truth anywhere.
    @sig.on_outcome
    def on_clip(clip_id, kept):
        return kept

    decision_ctx = _observe_under_span(sig, tracer_provider, "clip-1", "resp-1")
    exporter.clear()

    passthrough = on_clip("clip-1", True)  # the app's signal fires
    assert passthrough is True  # handler return value is passed through untouched

    span = exporter.get_finished_spans()[0]
    assert span.name == "gen_ai.evaluation.result"
    assert span.attributes["augmentloop.grade.source"] == "reality"
    assert span.attributes["gen_ai.evaluation.score.label"] == "correct"
    assert span.attributes["gen_ai.response.id"] == "resp-1"
    # Span-link Role 1: the late grade links back to the decision span.
    assert span.links[0].context.span_id == decision_ctx.span_id


def test_negative_signal_grades_incorrect(tracer_provider, exporter):
    sig = RealitySignal("clip.kept", tracer_provider=tracer_provider)

    @sig.on_outcome
    def on_clip(clip_id, kept):
        return kept

    _observe_under_span(sig, tracer_provider, "clip-2", "resp-2")
    exporter.clear()

    on_clip("clip-2", False)  # discarded
    span = exporter.get_finished_spans()[0]
    assert span.attributes["gen_ai.evaluation.score.label"] == "incorrect"
    assert span.attributes["gen_ai.evaluation.score.value"] == 0.0


def test_positive_maps_a_non_boolean_signal(tracer_provider, exporter):
    # A thumbs signal that is +1 / -1 rather than a bool: one per-signal line,
    # still no per-decision checker.
    sig = RealitySignal(
        "answer.helpful",
        positive=lambda rating: rating > 0,
        tracer_provider=tracer_provider,
    )
    _observe_under_span(sig, tracer_provider, "msg-1", "resp-3")
    exporter.clear()

    assert sig.record("msg-1", 1) is True
    assert exporter.get_finished_spans()[0].attributes[
        "gen_ai.evaluation.score.label"
    ] == "correct"


def test_unobserved_key_records_nothing(tracer_provider, exporter):
    sig = RealitySignal("clip.kept", tracer_provider=tracer_provider)
    # A signal fires for a key we never observed - no decision, no grade.
    assert sig.record("never-seen", True) is False
    assert exporter.get_finished_spans() == ()


def test_each_decision_grades_once(tracer_provider, exporter):
    sig = RealitySignal("clip.kept", tracer_provider=tracer_provider)
    _observe_under_span(sig, tracer_provider, "clip-3", "resp-4")
    exporter.clear()

    assert sig.record("clip-3", True) is True   # first signal grades
    assert sig.record("clip-3", True) is False  # replays don't double-count
    assert len(exporter.get_finished_spans()) == 1


def test_cross_process_via_serialized_ids(tracer_provider, exporter):
    # Decision observed in "process A"; outcome arrives in "process B" that only
    # has the persisted ids. A store swap is all it takes - still no checker.
    persisted: dict = {}

    class SerializingStore:
        def put(self, key, ref):
            persisted[key] = ref_to_ids(ref)

        def pop(self, key):
            ids = persisted.pop(key, None)
            return ref_from_ids(ids) if ids else None

    sig = RealitySignal(
        "appointment.landed",
        store=SerializingStore(),
        tracer_provider=tracer_provider,
    )
    decision_ctx = _observe_under_span(sig, tracer_provider, "appt-1", "resp-5")
    exporter.clear()

    assert persisted["appt-1"]["response_id"] == "resp-5"  # survived as primitives
    assert sig.record("appt-1", True) is True

    span = exporter.get_finished_spans()[0]
    assert span.attributes["augmentloop.grade.source"] == "reality"
    assert span.links[0].context.trace_id == decision_ctx.trace_id
    assert span.links[0].context.span_id == decision_ctx.span_id


def test_serialized_ids_survive_a_real_json_round_trip(tracer_provider, exporter):
    """The store is Redis or a database, so the ids go through actual JSON.

    The test above round-trips a Python dict, which cannot fail this way: Python
    ints are arbitrary precision. Real JSON consumed by anything with IEEE 754
    numbers (`JSON.parse` holds integers exactly only to 2**53 - 1) would silently
    round a 128-bit trace id to a different trace id, and the span link would then
    point at a trace that does not exist.
    """
    persisted: dict = {}

    class JsonStore:
        def put(self, key, ref):
            persisted[key] = json.dumps(ref_to_ids(ref))

        def pop(self, key):
            blob = persisted.pop(key, None)
            return ref_from_ids(json.loads(blob)) if blob else None

    sig = RealitySignal(
        "appointment.landed",
        store=JsonStore(),
        tracer_provider=tracer_provider,
    )
    decision_ctx = _observe_under_span(sig, tracer_provider, "appt-2", "resp-6")
    exporter.clear()

    ids = json.loads(persisted["appt-2"])
    assert isinstance(ids["trace_id"], str) and len(ids["trace_id"]) == 32
    assert isinstance(ids["span_id"], str) and len(ids["span_id"]) == 16
    assert int(ids["trace_id"], 16) == decision_ctx.trace_id
    assert decision_ctx.trace_id > 2**53 - 1, "a real trace id exceeds JS exact-int range"

    assert sig.record("appt-2", True) is True
    span = exporter.get_finished_spans()[0]
    assert span.links[0].context.trace_id == decision_ctx.trace_id
    assert span.links[0].context.span_id == decision_ctx.span_id


def test_ref_from_ids_still_reads_the_legacy_raw_int_form():
    # A store written before the hex change keeps working.
    ref = ref_from_ids({"trace_id": 12345678901234567890, "span_id": 1234567890, "response_id": "r"})
    assert ref.span_context.trace_id == 12345678901234567890
    assert ref.span_context.span_id == 1234567890
