# ToyWorld World-First Product Film — Revised Design

## Objective

Create a hackathon-winning product film that makes the real ToyWorld environment
the visual centerpiece while explaining the broader Gradebook thesis. Duration
is determined by clarity rather than a fixed limit; the target range is 100–120
seconds.

## Audience and Message

The primary audience is hackathon judges. The film must impress them with the
3D Pune world, then show why it exists:

> AI systems should be measured by the correctness and cost of their decisions,
> not described as “working well” without evidence.

ToyWorld is the transparent proving ground. Gradebook is the reusable
instrumentation layer that turns the world’s decisions into trustworthy,
observable evidence.

## Story

1. Introduce the real 3D Pune environment through a cinematic orbit.
2. Explain the observability problem: requests and latency do not establish
   whether an AI decision was correct or worth its cost.
3. Establish ToyWorld as a controlled experiment: seven models navigate 20
   junctions and make 420 route-choice, ETA-estimate, and next-hop decisions.
4. Explain the live visual language:
   - model-specific agent colors;
   - green correct routes;
   - red wrong routes;
   - yellow optimal alternatives;
   - deferred real-world outcomes.
5. Follow one agent and connect its visible choice to a machine-checkable grade.
6. Reveal Gradebook: standard OpenTelemetry evaluation events, deterministic or
   reality-based authority, decision pricing, and outcome-to-decision links.
7. Show the completed run and its measurable results: correctness, total cost,
   and cost per correct decision.
8. End on the broader result: the same layer can make any AI system measurable
   when its decisions have deterministic checks or observable outcomes.

## Real Website Recording

The real `viewer` application is the primary visual for approximately 85–90% of
the film. Record at 1920×1080 using the existing Three.js viewer and its actual
data.

Capture deliberate passes:

- slow orbit over Pune while introducing the environment;
- top-down view for junction and route comprehension;
- street camera as agents begin navigating;
- follow-selected-agent view for one concrete decision;
- overview during multi-model comparison;
- HUD-focused framing as decisions, correctness, cost, and cost per correct
  decision accumulate;
- completed-run framing with all 420 decisions and final totals.

Run the replay at 4× where useful, but camera motion must remain smooth. Cursor
movement must be deliberate. No simulated product interface may substitute for
the actual viewer.

## Graphics

Use restrained overlays only:

- short chapter titles;
- a small number of metric callouts;
- gentle crops or magnification for important HUD values;
- premium Gradebook identity treatment at the opening and close.

Overlays must never obscure the 3D world or make the footage look staged.

## Narration

Use one continuous presenter-style script. Generate paragraph-length narration
or tightly crossfade shorter clauses. There must be no long silent gaps between
story beats.

Natural sentence breaths are allowed, but narration should continue across
camera changes and graphic transitions. The voice must explain what is visible,
why it matters, and how it supports the Gradebook conclusion.

## Audio

- Retain the selected warm Kokoro voice unless a continuous-script audition
  shows a clearly better available voice.
- Keep one soft technology music bed running for the whole film.
- Duck music smoothly under narration.
- Use sparse effects only for significant camera, route, result, or identity
  moments.
- Target approximately −14 LUFS integrated and no more than −1 dBTP.
- Export 48 kHz stereo AAC.

## Synchronization

Create a new frame-addressed cue sheet for the actual final duration. It is the
single source of truth for:

- footage clip ranges;
- camera-pass selection;
- narration and caption timing;
- overlays;
- music automation;
- effects.

Narration begins within the opening seconds and continues through the story.
Every visual change must occur under relevant speech rather than inside an
unexplained pause.

## Validation

The revised film is complete only when:

1. The primary footage is a recording of the actual ToyWorld viewer.
2. The film visibly includes orbit, top-down, street, follow-agent, HUD, and
   completed-result views.
3. Narration explains the environment, problem, purpose, experiment, Gradebook
   mechanism, result, and broader applicability.
4. Automated silence detection finds no unintended long narration gaps.
5. Captions match the narration.
6. Footage and narration topics align at every chapter boundary.
7. Final video and audio start at zero and have equal duration.
8. The output is 1920×1080 H.264 High Profile with 48 kHz stereo AAC.
9. A full playback review confirms that the world—not abstract graphics—is the
   memorable centerpiece.

## Out of Scope

- Rebuilding the ToyWorld viewer for the video.
- Inventing results not present in the committed run.
- Filling time with generic dashboard mockups.
- Keeping the previous 60-second duration at the expense of explanation.
