# Visuals

Renders over telemetry this build already emits. No new instrumentation, no
synthetic data: `capture_run.py` runs the same `toyworld.replay` through the
same Gradebook library and swaps only the exporter for an in-memory one, the
way the test suite does. Every span, attribute and span link in `run-data.js`
is the one that would have gone to SigNoz.

They are static files, so they open with a double-click and need no server, no
SigNoz, and no API key.

## Blast radius

When reality proves one decision wrong, every decision taken after it was made
in the world that wrong decision produced. This walks the conventions §6 span
link from a reality verdict back to the decision it judges, then forward
through the journey, and prices what sits inside the radius.

![Blast radius, rendered from the committed replay recording on 2026-07-25: reality proved driver-3 arrived late, the verdict span-links back to the junction J1 decision, and the two decisions after it are shown inside the radius](blast-radius.png)

Reality proved `driver-3` arrived late. The verdict lives in a different trace
and a different service (`toy-world-outcomes`), and links back across that
boundary to `junction J1 decision`, where `google/gemini-2.0-flash` chose route
B at 9.0m over the true fastest A at 7.0m. The two junctions after it are
inside the radius: **3 of 3 decisions in the journey, $0.000079 of spend from
the disproved decision onward.** Click any of the four verdicts to re-seed it -
`driver-4`'s origin is J2, so J1 stays outside the radius, and the two on-time
verdicts show what a clean radius looks like.

The span link is the point. It is the piece of architecture that makes a late,
cross-service, cross-trace verdict attributable to the decision that earned it,
and it is otherwise invisible plumbing.

## Regenerating

```bash
pip install -e reference-library -e toy-world
python docs/visuals/capture_run.py     # rewrites run-data.js from a fresh run
```

Then open `docs/visuals/blast-radius.html`. The replay is deterministic, so the
numbers do not move between runs; only the trace and span ids do.
