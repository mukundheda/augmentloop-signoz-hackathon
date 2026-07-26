# Gradebook and ToyWorld 60-Second Product Demo — Audiovisual Design

## Objective

Create a professional 60-second product demo in which ToyWorld is the interactive
learning environment and Gradebook converts learner activity into clear,
actionable guidance. The result must feel restrained, premium, and coherent,
with frame-accurate synchronization between visuals, narration, music, effects,
and captions.

## Creative Direction

- Narrator: warm, confident female product presenter.
- Music: minimal premium technology; soft synth pulse, subtle piano, restrained
  momentum, and one gentle lift near the product payoff.
- Sound design: sparse and tactile. Use effects only to reinforce meaningful
  transitions, interactions, insights, and the closing identity.
- Visual hierarchy: ToyWorld creates the activity; Gradebook creates the
  understanding. They are one product story, not two competing products.

## Story Structure

| Time | Story beat | Audio intent |
| --- | --- | --- |
| 0–6s | ToyWorld opens and establishes the learning environment | Soft identity tone and first narration phrase |
| 6–18s | Learners interact and generate meaningful activity | Quiet rhythmic pulse and restrained UI sounds |
| 18–34s | Gradebook converts activity into progress signals | Subtle transition whoosh; narration remains dominant |
| 34–48s | Teacher sees strengths, gaps, and next actions | Music develops slightly; insight accents land on UI events |
| 48–56s | Less manual grading and clearer decisions | Gentle musical lift under the primary product payoff |
| 56–60s | Gradebook and ToyWorld closing identity | Narration resolves; short, restrained sonic logo |

## Voice Pipeline

Use Kokoro-82M through `kokoro-js` with WebAssembly inference. This avoids the
native PyTorch DLLs blocked by Windows Application Control and requires no API
key or subscription.

Generate the narration sentence by sentence rather than as one long file.
Produce auditions using `af_heart`, `af_bella`, and at least two additional
appropriate female voices. Choose the voice based on intelligibility, warmth,
confidence, and consistency rather than generation speed.

Each selected sentence is exported as WAV. Insert deliberate pauses in the cue
sheet instead of relying on incidental silence from the model. Apply restrained
high-pass filtering, corrective EQ, de-essing, compression, and loudness
normalization with FFmpeg. Do not use aggressive denoising on clean generated
speech.

## Music and Sound Effects

Select one minimal-technology instrumental from Mixkit under the applicable
Mixkit Free License. Preserve the asset title, creator, source URL, download
date, and license URL in an asset manifest.

Select a small set of licensed effects from the same source where possible:

- opening identity texture;
- two quiet interface interactions;
- one transition whoosh;
- one insight accent;
- one closing chime.

Avoid trailer impacts, frequent whooshes, prominent clicks, or effects that
compete with speech. Keep original downloaded assets in a source-assets folder
and render processed derivatives separately.

## Synchronization Architecture

Use a single machine-readable cue sheet as the source of truth. Every cue uses
integer frame boundaries at 30 fps and includes:

- visual scene identifier;
- narration file and start frame;
- caption text and frame range;
- music automation points;
- sound-effect file, start frame, gain, and optional fade;
- expected scene end frame.

The video renderer and audio mixer both consume this cue sheet. Time values for
FFmpeg are derived from `frame / 30`; hand-entered decimal timestamps are not
allowed. Narration duration is measured with `ffprobe` after generation.
Visual scene boundaries are adjusted to the measured narration, while the total
timeline remains exactly 1,800 frames.

The mix must begin at timestamp zero, use a 48 kHz audio clock, and finish at
exactly 60 seconds. The final mux must not use `-shortest`, because that can
silently truncate either stream.

## Mix and Master

- Narration stays centered and is always the dominant element.
- Music is stereo and remains approximately 18–24 dB below narration during
  spoken passages.
- Use sidechain compression or cue-based gain automation to duck music beneath
  speech, with smooth attack and release.
- Effects are placed at exact cue frames and remain quieter than narration.
- Apply final two-pass loudness normalization targeting approximately −14 LUFS
  integrated and no higher than −1 dBTP for web playback.
- Export H.264 High Profile video with 48 kHz AAC stereo audio and fast-start
  metadata.

## Validation

The production is complete only when all checks pass:

1. Kokoro generates every selected narration segment without a native-policy
   failure.
2. All audio assets have recorded source and license information.
3. Cue ranges are ordered, within 0–1,799, and do not overlap illegally.
4. Captions match the final spoken script.
5. The rendered video contains exactly 1,800 frames at 30 fps.
6. Final audio is exactly 48 kHz stereo and matches the 60-second timeline.
7. Automated checks report no audio/video start-time drift.
8. Review frames at each cue boundary match the intended spoken phrase or sound.
9. A full playback review confirms intelligibility, tasteful music ducking,
   restrained effects, and a clean ending.

## Failure Handling

If Kokoro.js WebAssembly is blocked or unstable, use Sherpa-ONNX WebAssembly
with Kokoro as the fallback. Piper is reserved for diagnostics because its
voice quality is not suitable for the final product demo.

If no suitable Mixkit track can be downloaded with clear license metadata,
use a Pixabay track with equivalent metadata. Do not use an asset whose
licensing cannot be documented.
