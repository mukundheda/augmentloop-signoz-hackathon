export function frameToMilliseconds(frame, fps) {
  return Math.round((frame * 1000) / fps);
}

export function buildAudioGraph({fps, totalFrames = fps * 60, narration, effects}) {
  const duration = totalFrames / fps;
  const fadeOutStart = Math.max(0, duration - 4);
  const parts = [
    `[0:a]atrim=0:${duration},aresample=48000,volume=0.085,` +
      `afade=t=in:st=0:d=1.4,afade=t=out:st=${fadeOutStart}:d=4[music]`,
  ];

  narration.forEach((cue, index) => {
    const delay = frameToMilliseconds(cue.startFrame, fps);
    parts.push(
      `[${index + 1}:a]aresample=48000,highpass=f=75,lowpass=f=15500,` +
      `acompressor=threshold=0.11:ratio=2.6:attack=8:release=100:makeup=1.3,` +
      `adelay=${delay}|${delay}[voice${index}]`,
    );
  });
  const voiceLabels = narration.map((_, index) => `[voice${index}]`).join("");
  parts.push(
    `${voiceLabels}amix=inputs=${narration.length}:duration=longest:normalize=0,` +
      `apad=whole_dur=${duration}[voices]`,
  );
  parts.push("[voices]asplit=2[voicekey][voiceout]");
  parts.push(
    "[music][voicekey]sidechaincompress=threshold=0.018:ratio=8:attack=25:release=320:makeup=1[ducked]",
  );

  effects.forEach((cue, index) => {
    const input = narration.length + 1 + index;
    const delay = frameToMilliseconds(cue.startFrame, fps);
    const gain = 10 ** (cue.gainDb / 20);
    parts.push(
      `[${input}:a]aresample=48000,volume=${gain.toFixed(5)},adelay=${delay}|${delay}[sfx${index}]`,
    );
  });

  const effectLabels = effects.map((_, index) => `[sfx${index}]`).join("");
  parts.push(
    `[ducked][voiceout]${effectLabels}amix=inputs=${effects.length + 2}:duration=longest:normalize=0,` +
    `apad=whole_dur=${duration},atrim=duration=${duration},` +
      "asetpts=N/SR/TB,aresample=48000[mix]",
  );
  return parts.join(";");
}
