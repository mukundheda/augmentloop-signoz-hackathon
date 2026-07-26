const REQUIRED_CAMERA_MODES = ["orbit", "top", "chase", "follow", "overview"];

export function validateWorldFirstDelivery({probe, cues, recording, narration}) {
  const video = probe.streams.find((stream) => stream.codec_type === "video");
  const audio = probe.streams.find((stream) => stream.codec_type === "audio");
  if (!video || !audio) throw new Error("master must contain video and audio streams");

  const expectedDuration = cues.totalFrames / cues.fps;
  exact(video.codec_name, "h264", "video codec");
  exact(video.profile, "High", "video profile");
  exact(video.width, cues.width, "video width");
  exact(video.height, cues.height, "video height");
  exact(video.r_frame_rate, `${cues.fps}/1`, "video frame rate");
  exact(Number(video.nb_read_frames), cues.totalFrames, "video frames");
  close(Number(video.start_time), 0, "video start");
  close(Number(video.duration), expectedDuration, "video duration");

  exact(audio.codec_name, "aac", "audio codec");
  exact(Number(audio.sample_rate), 48000, "audio sample rate");
  exact(audio.channels, 2, "audio channels");
  close(Number(audio.start_time), 0, "audio start");
  close(Number(audio.duration), expectedDuration, "audio duration");
  close(Number(probe.format.duration), expectedDuration, "container duration");

  const cameraModes = [...new Set(
    recording.actions
      .filter((action) => action.operation === "camera")
      .map((action) => action.value),
  )].sort();
  for (const mode of REQUIRED_CAMERA_MODES) {
    if (!cameraModes.includes(mode)) throw new Error(`missing real viewer camera mode: ${mode}`);
  }
  exact(recording.finalStatus?.state, "COMPLETE", "recording final state");

  const narrationById = new Map(narration.map((cue) => [cue.id, cue]));
  for (const cue of cues.narration) {
    exact(narrationById.get(cue.id)?.text, cue.text, `narration text for ${cue.id}`);
  }

  return {
    durationSeconds: expectedDuration,
    frames: cues.totalFrames,
    cameraModes,
    video: {
      codec: video.codec_name,
      profile: video.profile,
      width: video.width,
      height: video.height,
      fps: cues.fps,
    },
    audio: {
      codec: audio.codec_name,
      sampleRate: Number(audio.sample_rate),
      channels: audio.channels,
    },
  };
}

function exact(actual, expected, label) {
  if (actual !== expected) throw new Error(`expected ${expected} ${label}, received ${actual}`);
}

function close(actual, expected, label) {
  if (!Number.isFinite(actual) || Math.abs(actual - expected) > 0.001) {
    throw new Error(`expected ${expected} ${label}, received ${actual}`);
  }
}
