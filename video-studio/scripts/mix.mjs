import {spawnSync} from "node:child_process";
import {mkdir, readFile} from "node:fs/promises";
import path from "node:path";
import {buildAudioGraph} from "../src/audio-graph.mjs";

const root = process.cwd();
const cues = JSON.parse(await readFile(path.join(root, "timeline", "cues.json"), "utf8"));
const narration = JSON.parse(await readFile(path.join(root, "output", "audio", "narration.json"), "utf8"));
const assets = JSON.parse(await readFile(path.join(root, "assets", "audio", "manifest.json"), "utf8"));
const byId = new Map(assets.assets.map((asset) => [asset.id, asset]));
const outputDir = path.join(root, "output", "audio");
const premaster = path.join(outputDir, "premaster.wav");
const master = path.join(outputDir, "master.wav");
await mkdir(outputDir, {recursive: true});

const inputs = [
  byId.get(cues.music.assetId).path,
  ...narration.map((cue) => cue.file),
  ...cues.effects.map((cue) => byId.get(cue.assetId).path),
];
const inputArgs = inputs.flatMap((file) => ["-i", path.join(root, file)]);
const graph = buildAudioGraph({fps: cues.fps, narration, effects: cues.effects});

let result = spawnSync(
  "ffmpeg",
  ["-y", ...inputArgs, "-filter_complex", graph, "-map", "[mix]", "-c:a", "pcm_s24le", premaster],
  {stdio: "inherit"},
);
if (result.status !== 0) throw new Error(`premaster mix failed (${result.status})`);

result = spawnSync(
  "ffmpeg",
  [
    "-y", "-i", premaster,
    "-af", "loudnorm=I=-11.5:LRA=9:TP=-2,alimiter=limit=0.88:attack=5:release=80:level=false",
    "-ar", "48000", "-ac", "2", "-c:a", "pcm_s24le", master,
  ],
  {stdio: "inherit"},
);
if (result.status !== 0) throw new Error(`mastering failed (${result.status})`);
console.log(`Created ${master}`);
