# Gradebook 60-Second Product Demo

## Purpose

Create a professional, judge-facing 60-second explainer that introduces Gradebook through the Pune ToyWorld demo. The video must make the core value proposition understandable without requiring prior knowledge of OpenTelemetry or SigNoz. This cut will also serve as the evaluation prototype for a later three-minute product film.

## Audience and format

- Primary audience: Agents of SigNoz hackathon judges
- Secondary audience: engineers evaluating AI observability tools
- Runtime: 60 seconds
- Frame: 16:9, 1920×1080
- Delivery: MP4 with professional English narration, burned-in captions, and subtle electronic background music
- Tone: credible, technical, polished, and concise

## Narrative

The story moves from an industry problem to a visible demonstration, then to trustworthy telemetry and a concrete result:

1. AI quality is often asserted rather than measured.
2. In ToyWorld, AI drivers make three kinds of decisions while navigating Pune.
3. Gradebook records each decision as standard OpenTelemetry telemetry and identifies where every grade's authority came from.
4. Deterministic math and delayed reality outcomes remain distinct; AI-judge opinion never enters the headline metric.
5. SigNoz exposes the resulting traces, metrics, logs, dashboards, and alerts.
6. The committed run demonstrates the headline result and the need to right-size models by decision type.
7. Humans retain control over any routing change.

## Time-coded storyboard

### 0:00–0:06 — Hook

Visual: dark background, restrained telemetry motion, then the Gradebook title.

Narration: “AI performance shouldn’t be an assertion. It should be a measurement.”

On-screen text: `GRADEBOOK` and `Evidence for every AI decision`

### 0:06–0:16 — ToyWorld

Visual: Pune ToyWorld overview followed by moving agents. Brief callouts identify `route_choice`, `eta_estimate`, and `next_hop`.

Narration: “In our Pune ToyWorld, seven AI models navigate the same roads—choosing routes, estimating arrival times, and selecting their next hop.”

### 0:16–0:29 — Grade provenance

Visual: transition from an active route into an evaluation event, then the provenance strip. Blue represents math and amber represents reality.

Narration: “Gradebook records every decision as an OpenTelemetry evaluation event, stamped with its source: deterministic math now, or a real-world outcome that arrives later.”

### 0:29–0:40 — Trust boundary

Visual: math and reality lanes remain prominent while an `ai_judge` lane is visibly separated and excluded from the headline calculation. A linked reality outcome overturns one route.

Narration: “Model opinions stay labeled and separate. They never silently enter the headline number—and reality can overturn the original checker.”

### 0:40–0:51 — SigNoz

Visual: clean montage of traces, metrics, logs, dashboards, and alert rules, with the cost-per-correct-decision panel as the focal point.

Narration: “SigNoz turns that evidence into traces, metrics, logs, dashboards, and alerts—including the metric that matters: cost per correct decision.”

### 0:51–0:57 — Result

Visual: large numerical callouts over a subdued ToyWorld background.

Narration: “Across 420 decisions: 268 correct, forty cents spent, and point-zero-zero-one-five-zero-seven dollars per correct decision.”

On-screen text:

- `420 decisions`
- `268 correct`
- `$0.403804 spent`
- `$0.001507 / correct decision`

### 0:57–1:00 — Close

Visual: Gradebook mark and a compact diagram from AI decision to trusted evidence to SigNoz.

Narration: “Gradebook. Measure what your AI gets right, what it costs, and why.”

## Visual system

- Background: near-black observability interface
- Primary accent: blue for deterministic math
- Secondary accent: amber for reality outcomes
- Status accents: green for correct, red for wrong, yellow for the optimal ghost route
- Typography: modern sans serif with high contrast and generous spacing
- Motion: restrained camera easing, purposeful zooms, clean cross-dissolves, and short data-callout animations
- Existing project visuals and actual product footage take priority over decorative stock imagery

## Audio and accessibility

- Narration must remain clear at normal laptop volume and use a measured product-demo cadence.
- Music stays below narration and contains no distracting vocals.
- Captions reproduce narration accurately and remain within title-safe margins.
- Important meaning must not depend on color alone; labels accompany provenance and correctness colors.

## Production components

1. Capture or render ToyWorld sequences from the existing viewer.
2. Capture representative SigNoz product surfaces from the working project or use verified repository screenshots when live capture is unavailable.
3. Animate the title, telemetry transition, grade-provenance separation, result callouts, and end card.
4. Record or synthesize narration from the approved script.
5. Add subtle music, captions, transitions, and final audio normalization.
6. Export the 1080p MP4 and review the rendered file for timing, legibility, audio balance, and factual accuracy.

## Acceptance criteria

- Total duration is between 58 and 62 seconds.
- The video clearly explains both Gradebook and ToyWorld.
- All displayed metrics match the committed run.
- Grade provenance and the exclusion of AI-judge opinions are unambiguous.
- Product footage is readable at 1080p without pausing.
- Narration, captions, and visuals remain synchronized.
- The finished MP4 plays correctly and contains both video and audio streams.
- The result is suitable for reviewing pacing and creative direction before producing the three-minute version.
