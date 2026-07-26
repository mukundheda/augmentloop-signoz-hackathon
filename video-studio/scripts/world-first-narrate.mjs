import {spawnSync} from "node:child_process";
import {access, mkdir, writeFile} from "node:fs/promises";
import path from "node:path";
import {generateVoiceJobs} from "../src/browser-tts.mjs";
import {loadWorldFirstCues} from "../src/world-first-cues.mjs";

const root = process.cwd();
const cues = await loadWorldFirstCues();
const outputDir = path.join(root, "output", "world-first", "audio");
const narrationDir = path.join(outputDir, "narration");
await mkdir(narrationDir, {recursive: true});

const jobs = cues.narration.map((segment) => ({
  id: segment.id,
  text: segment.text,
  voice: cues.voice,
  speed: segment.speed,
  outputPath: path.join(narrationDir, `${segment.id}.wav`),
}));
const missingJobs = [];
for (const job of jobs) {
  try {
    await access(job.outputPath);
  } catch {
    missingJobs.push(job);
  }
}
if (missingJobs.length) await generateVoiceJobs(missingJobs, {port: 41913});

const narration = jobs.map((job) => {
  const probe = spawnSync(
    "ffprobe",
    [
      "-v", "error", "-show_entries", "format=duration",
      "-of", "default=nw=1:nk=1", job.outputPath,
    ],
    {encoding: "utf8"},
  );
  if (probe.status !== 0) throw new Error(probe.stderr);
  const cue = cues.narration.find((segment) => segment.id === job.id);
  const durationFrames = Math.ceil(Number(probe.stdout.trim()) * cues.fps);
  if (cue.startFrame + durationFrames > cue.endFrame) {
    throw new Error(
      `${cue.id} narration needs ${durationFrames} frames but only ` +
        `${cue.endFrame - cue.startFrame} are scheduled`,
    );
  }
  return {
    id: cue.id,
    file: path.relative(root, job.outputPath).replaceAll("\\", "/"),
    startFrame: cue.startFrame,
    endFrame: cue.startFrame + durationFrames,
    durationFrames,
    text: cue.text,
  };
});
await writeFile(
  path.join(outputDir, "narration.json"),
  `${JSON.stringify(narration, null, 2)}\n`,
);

const inputs = narration.flatMap((item) => ["-i", path.join(root, item.file)]);
const filters = narration.map((item, index) => {
  const delay = Math.round((item.startFrame * 1000) / cues.fps);
  return `[${index}:a]aresample=48000,adelay=${delay}|${delay}[n${index}]`;
});
const labels = narration.map((_, index) => `[n${index}]`).join("");
const duration = cues.totalFrames / cues.fps;
filters.push(
  `${labels}amix=inputs=${narration.length}:duration=longest:normalize=0,` +
    `apad=whole_dur=${duration},atrim=duration=${duration}[out]`,
);
const preview = path.join(outputDir, "narration-preview.wav");
const mixed = spawnSync(
  "ffmpeg",
  [
    "-y", ...inputs, "-filter_complex", filters.join(";"),
    "-map", "[out]", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", preview,
  ],
  {stdio: "inherit"},
);
if (mixed.status !== 0) throw new Error(`narration preview failed (${mixed.status})`);
console.log(`Created ${preview}`);
