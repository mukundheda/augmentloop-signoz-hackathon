import {spawnSync} from "node:child_process";
import {readFile, writeFile} from "node:fs/promises";
import path from "node:path";
import {assertNarrationDensity, parseSilenceDetect} from "../src/silence.mjs";
import {validateWorldFirstDelivery} from "../src/world-first-delivery.mjs";
import {loadWorldFirstCues} from "../src/world-first-cues.mjs";

const root = process.cwd();
const outputDir = path.join(root, "output", "world-first");
const master = path.join(outputDir, "gradebook-toyworld-world-first.mp4");
const narrationPreview = path.join(outputDir, "audio", "narration-preview.wav");
const cues = await loadWorldFirstCues();
const recording = JSON.parse(
  await readFile(path.join(outputDir, "footage", "recording.json"), "utf8"),
);
const narration = JSON.parse(
  await readFile(path.join(outputDir, "audio", "narration.json"), "utf8"),
);

const probeResult = run("ffprobe", [
  "-v", "error", "-count_frames",
  "-show_entries",
  "format=duration:stream=codec_type,codec_name,profile,width,height,r_frame_rate,sample_rate,channels,nb_read_frames,start_time,duration",
  "-of", "json", master,
]);
const delivery = validateWorldFirstDelivery({
  probe: JSON.parse(probeResult.stdout),
  cues,
  recording,
  narration,
});

const loudnessResult = run("ffmpeg", [
  "-hide_banner", "-i", master,
  "-af", "ebur128=peak=true", "-f", "null", "NUL",
], true);
const integratedMatches = [...loudnessResult.stderr.matchAll(/\bI:\s*(-?[\d.]+)\s+LUFS/g)];
const peakMatches = [...loudnessResult.stderr.matchAll(/\bPeak:\s*(-?[\d.]+)\s+dBFS/g)];
const integratedLufs = Number(integratedMatches.at(-1)?.[1]);
const truePeakDbfs = Number(peakMatches.at(-1)?.[1]);
if (!(integratedLufs >= -15 && integratedLufs <= -12.5)) {
  throw new Error(`integrated loudness ${integratedLufs} LUFS is outside -15 to -12.5`);
}
if (!(truePeakDbfs <= -1)) throw new Error(`true peak ${truePeakDbfs} dBFS exceeds -1 dBFS`);

const silenceResult = run("ffmpeg", [
  "-hide_banner", "-i", narrationPreview,
  "-af", "silencedetect=noise=-45dB:d=1.4", "-f", "null", "NUL",
], true);
const longSilences = parseSilenceDetect(silenceResult.stderr);
assertNarrationDensity(longSilences, 1.4);

const report = {
  passed: true,
  generatedAt: new Date().toISOString(),
  ...delivery,
  loudness: {integratedLufs, truePeakDbfs},
  narration: {
    voice: cues.voice,
    cues: narration.length,
    maximumAllowedGapSeconds: 1.4,
    detectedLongGaps: longSilences,
  },
  source: {
    app: recording.sourceApp,
    url: recording.sourceUrl,
    finalStatus: recording.finalStatus,
  },
};
const reportPath = path.join(outputDir, "verification.json");
await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify(report, null, 2));
console.log(`Verified ${master}`);

function run(command, args, acceptNonZero = false) {
  const result = spawnSync(command, args, {encoding: "utf8"});
  if (result.error) throw result.error;
  if (result.status !== 0 && !acceptNonZero) {
    throw new Error(`${command} failed (${result.status}): ${result.stderr}`);
  }
  return result;
}
