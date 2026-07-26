# Gradebook × ToyWorld Video Studio

Local, repeatable production pipeline for the 60-second Gradebook product demo.
It uses browser-based Kokoro-82M WASM narration, frame-addressed HTML motion,
Playwright capture, and FFmpeg mixing/mastering. It needs no API key.

## Setup

```powershell
npm.cmd install
npm.cmd run audition
npm.cmd run narrate
```

The selected voice is `af_heart`. Original Mixkit downloads live in the ignored
`assets/audio/source/` directory; their titles, URLs, and license are recorded
in `assets/audio/manifest.json`.

## Production

```powershell
npm.cmd run review:frames
npm.cmd run mix
npm.cmd run render
npm.cmd test
npm.cmd run check
```

The single timeline source of truth is `timeline/cues.json` (1,800 frames at
30 fps). The production master is:

`output/gradebook-toyworld-60s-mastered.mp4`

Expected delivery properties: 1920×1080 H.264 High Profile, 30 fps, 1,800
frames, 48 kHz stereo AAC, and exactly 60.000 seconds.
