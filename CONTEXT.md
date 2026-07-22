# Glossary

The shared language for this build. If a word here is used differently in an issue, PR, or conversation, the glossary wins until we change it together.

## Decision
One AI choice made by an agent that has a right answer we can check by machine. The atomic unit of the whole build. Every decision becomes one span.

## Grade
The verdict on a decision: was it correct, given what the agent could know at the time? Emitted as the standard OpenTelemetry `gen_ai.evaluation.result` event, never a custom schema. Every grade is stamped with its **grade source**.

## Grade source
Where a grade's authority comes from. Three kinds: **math** (a checker computes the provably right answer, e.g. the toy world's fastest route), **reality** (the outcome later proves it, e.g. the appointment actually landed on the calendar), and **AI judge** (another model scored it - an opinion, not a fact). Decided 2026-07-20: the headline metric, cost per correct decision, counts math and reality grades only; AI-judge grades appear only as a clearly labeled secondary view. See ADR 0001.

## Cost
What that decision cost in money (tokens priced per model). The headline metric of the build is cost per correct decision.

## Gradebook (the foundation layer)
The product's working name (decided 2026-07-20). The portable instrumentation layer we ship: generic span and metric names (decision, outcome, grade, cost) plus the grading and pricing plumbing. Deliberately knows nothing about traffic, video editing, or phone calls - any system that makes checkable AI decisions can wear it. Ships as two artifacts (decided 2026-07-20): the **conventions doc** (the recording rules, followable in any language) and the **reference library** (a Python package that applies the rules with one wrapper line; powers the toy world).

## Substrate
The real system the foundation layer is proven on. The substrate appears in the blog and screencast only, never in the repo, which goes public (exception: an open-source substrate may ship inside the repo). Decided 2026-07-20, updated 2026-07-21 after the Vedant AI-touchpoint call. The ladder:

- **Primary (LOCKED 2026-07-21): CleanCut** (Vedant's SaaS, revenue-generating, family-owned so no consent wall). The Jul 21 call confirmed real machine-checkable decisions, all inference server-side (the site's "processing local on device" line does not describe where the models run). Headline decisions = **filler-word detection** and **quote extraction**: both currently run on premium models (Claude / GPT-4o), both are math-gradeable (filler-words against a lexical check, quotes via a verbatim-substring check), so they double as the right-sizing targets (rerun the same decision on cheaper models and compare cost per correct). **Clip scoring** (predicted viral_score vs kept-or-discarded) is the reality-grade example - an honest proxy for real engagement, which is too slow to land inside the week.
- **Fallback if CleanCut's data proves too thin: an open-source agent on a checkable benchmark.** First choice tau-bench (Sierra; grade is deterministic - final database state vs a gold answer; cheap; a tool-calling agent, which is the most observability-native thing to watch). Heavier option: OpenHands + SWE-bench-Mini (50 tasks; OpenHands emits OpenTelemetry natively; reality grade = the test suite passes). Advantage over CleanCut for reproducibility: being open source, it can run inside the public repo the judges re-run, not only in the blog. All calls on cheap models via OpenRouter, small subsets, replay by default.
- **Floor:** Mukund's own AugmentLoop internal systems (real, owned, no consent wall).

Client systems are ruled out this week (public repo + consent + contract walls) and banked as the post-hackathon service. A hard requirement at every rung: the layer is always proven on a proper real system, never only on the toy world.

## Model roster
The models competing in the comparison. Default (decided 2026-07-20, explicitly low-stakes and changeable): Claude Haiku, Claude Sonnet, Gemini Flash - two price tiers within one provider (the right-sizing story) plus a cross-provider contrast. Access via OpenRouter so any model can be swapped in later; no local model (ops friction, no judge value). All calls on API keys with per-run budget caps, never team Max plans.

## Voice entrance
The closing demo beat, whose point is ACCESSIBILITY (the organizers' named pain: telemetry is unreachable from a phone): an alert fires, the on-call's phone rings, a voice agent that reads SigNoz live briefs the incident, and the human approves the fix by voice. Guardrails (decided 2026-07-20): one day-2 chain verify plus at most half a day of build; shown as one recorded real call in the screencast, never live; cut without debate if the chain is not proven by end of Jul 24 (approval then stays in chat/terminal, which still satisfies "agents propose, humans decide"). A crowd feature by design - it is the entrance to the moat, never the moat.

## Span link roles
Two uses of SigNoz span links (decided 2026-07-20). Role 1, foundation and mandatory: a grade that arrives after the fact (reality grades) links back to the decision it judges - required by the conventions doc on every substrate. Role 2, world and bonus: agent-to-agent cause and effect inside the toy world or sim skin.

## Right-sizing
The hero action of the propose-approve-apply loop (decided 2026-07-20): the MCP agent reads cost per correct decision by model, proposes rerouting a decision type to a cheaper model, a human approves, and the next run proves quality held while cost dropped. SigNoz-side writes (alerts, dashboards, views) are the supporting actions around it.

## Meta panel
One bounded dashboard panel where the layer grades the agents building this project: each ticket's Claude Code session is a decision, spec-review plus test-suite outcome is its reality grade, so cost per correct decision applies to our own build fleet. Capped at one panel; a third proof surface, never a substitute for the substrate.

## Demo harness (the toy world)
The small stand-in program committed in this repo. Judges re-run casting.yaml, run the toy world, and the dashboards light up on their machine. Chosen 2026-07-20: a tiny world of ~3 junctions with a few AI drivers picking routes; the toy knows the true fastest route, so every decision is auto-gradeable. Doubles as the seed of the sim skin. Revisitable if it fights us. Ships in two modes: replay (default - recorded decisions, deterministic, judges need no API keys) and live (bring your own OpenRouter key).

## Skin
A presentation world layered on top of the foundation (e.g. the Pune corridor sim). Changes what the story looks like, never what the foundation measures.

## Skin gate
The explicit team decision on whether to build the sim skin, evaluated Jul 23 evening (decided 2026-07-20) so a yes gives Vedant the Jul 24 Swans day for engine work. Four checks: (1) foundation done on the toy world - graded, priced, dashboards, one alert firing, one clean casting.yaml re-run from scratch; (2) substrate resolved - SaaS integration verified or officially killed; (3) right-sizing hero moment demoed end to end once; (4) two clear Vedant-days left and API budget green. Ruling: 4 green = build a full skin; 3 green = smaller skin (dress up the toy world); under 3 = no skin, remaining days go to polish, blog, and screencast. The gate also picks WHICH skin (noted 2026-07-20): Pune traffic is the lead candidate, not a commitment - alternatives (war room, epidemic, evacuation, market crash, or something new) are reviewed at the gate once the foundation is real.
