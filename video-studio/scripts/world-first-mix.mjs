import {spawnSync} from "node:child_process";
import {mkdir, readFile} from "node:fs/promises";
import path from "node:path";
import {buildAudioGraph} from "../src/audio-graph.mjs";
import {loadWorldFirstCues} from "../src/world-first-cues.mjs";

const root = process.cwd();
const cues = await loadWorldFirstCues();
const narration = JSON.parse(
  await readFile(path.join(root, "output", "world-first", "audio", "narration.json"), "utf8"),
);
const assets = JSON.parse(
  await readFile(path.join(root, "assets", "audio", "manifest.json"), "utf8"),
);
const byId = new Map(assets.assets.map((asset) => [asset.id, asset]));
const outputDir = path.join(root, "output", "world-first", "audio");
const premaster = path.join(outputDir, "premaster.wav");
const master = path.join(outputDir, "master.wav");
await mkdir(outputDir, {recursive: true});

const music = path.join(root, byId.get(cues.music.assetId).path);
const voiceFiles = narration.map((cue) => path.join(root, cue.file));
const effectFiles = cues.effects.map((cue) => path.join(root, byId.get(cue.assetId).path));
const inputArgs = [
  "-stream_loop", "-1", "-i", music,
  ...voiceFiles.flatMap((file) => ["-i", file]),
  ...effectFiles.flatMap((file) => ["-i", file]),
];
const graph = buildAudioGraph({
  fps: cues.fps,
  totalFrames: cues.totalFrames,
  narration,
  effects: cues.effects,
});

let result = spawnSync(
  "ffmpeg",
  [
    "-y", ...inputArgs, "-filter_complex", graph, "-map", "[mix]",
    "-c:a", "pcm_s24le", premaster,
  ],
  {stdio: "inherit"},
);
if (result.status !== 0) throw new Error(`world-first premaster failed (${result.status})`);

result = spawnSync(
  "ffmpeg",
  [
    "-y", "-i", premaster,
    "-af", "loudnorm=I=-13.5:LRA=9:TP=-2,alimiter=limit=0.88:attack=5:release=80:level=false",
    "-ar", "48000", "-ac", "2", "-c:a", "pcm_s24le", master,
  ],
  {stdio: "inherit"},
);
if (result.status !== 0) throw new Error(`world-first mastering failed (${result.status})`);
console.log(`Created ${master}`);
