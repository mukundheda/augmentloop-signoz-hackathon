# Gradebook / ToyWorld Video Studio

Local, repeatable production pipeline for the two-minute, world-first Gradebook
product film. It records the real ToyWorld website with deterministic camera
actions, generates continuous Kokoro-82M narration locally, and uses FFmpeg for
music ducking, effects, mastering, restrained titles, and delivery encoding. It
needs no API key.

## Setup

```powershell
npm.cmd install
npm.cmd run audition
```

The selected voice is `af_heart`. Original Mixkit downloads live in the ignored
`assets/audio/source/` directory; their titles, URLs, and license are recorded
in `assets/audio/manifest.json`.

## World-first production

```powershell
npm.cmd run world:build
npm.cmd test
npm.cmd run check
```

Individual stages are available as `world:narrate`, `world:record`, `world:mix`,
`world:master`, and `world:verify`. The single timeline source of truth is
`timeline/world-first-cues.json` (3,600 frames at 30 fps). The production
master is:

`output/world-first/gradebook-toyworld-world-first.mp4`

Expected delivery properties: 1920x1080 H.264 High Profile, 30 fps, 3,600
frames, 48 kHz stereo AAC, exactly 120.000 seconds, about -14 LUFS integrated,
and no narration gap longer than 1.4 seconds. The verification report is
written to `output/world-first/verification.json`.

The original 60-second pipeline remains available through `narrate`, `mix`,
`render`, and `review:frames`.
