import {spawnSync} from "node:child_process";
import {mkdir, readFile, writeFile} from "node:fs/promises";
import path from "node:path";
import {buildOverlayPlan} from "../src/overlay-plan.mjs";
import {loadWorldFirstCues} from "../src/world-first-cues.mjs";

const root = process.cwd();
const outputDir = path.join(root, "output", "world-first");
const footage = path.join(outputDir, "footage", "toyworld-live.webm");
const recording = JSON.parse(
  await readFile(path.join(outputDir, "footage", "recording.json"), "utf8"),
);
const audio = path.join(outputDir, "audio", "master.wav");
const assFile = path.join(outputDir, "overlays.ass");
const output = path.join(outputDir, "gradebook-toyworld-world-first.mp4");
const cues = await loadWorldFirstCues();
const overlays = buildOverlayPlan(cues);

await mkdir(outputDir, {recursive: true});
await writeFile(assFile, buildAss(overlays), "utf8");

const subtitlePath = path.relative(root, assFile).replaceAll("\\", "/");
const duration = cues.totalFrames / cues.fps;
const filter = [
  `[0:v]trim=start=${recording.readyOffsetSeconds}:duration=${duration}`,
  "setpts=PTS-STARTPTS",
  "tpad=stop_mode=clone:stop_duration=1",
  `fps=${cues.fps}`,
  `trim=duration=${duration}`,
  "setpts=PTS-STARTPTS",
  `scale=${cues.width}:${cues.height}:flags=lanczos`,
  `subtitles=filename='${subtitlePath}'`,
  "format=yuv420p[v]",
].join(",");

const result = spawnSync(
  "ffmpeg",
  [
    "-y", "-i", footage, "-i", audio,
    "-filter_complex", filter,
    "-map", "[v]", "-map", "1:a:0",
    "-frames:v", String(cues.totalFrames),
    "-c:v", "libx264", "-preset", "medium", "-crf", "18",
    "-profile:v", "high", "-level:v", "4.1", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
    "-movflags", "+faststart", output,
  ],
  {stdio: "inherit"},
);
if (result.status !== 0) throw new Error(`world-first master failed (${result.status})`);
console.log(`Created ${output}`);

function buildAss(events) {
  const header = `[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: chapter,Segoe UI Semibold,28,&H00FFFFFF,&H00FFFFFF,&H78070B15,&H78070B15,-1,0,0,0,100,100,1.2,0,3,12,0,7,64,520,118,1
Style: metric,Segoe UI Semibold,30,&H00FFFFFF,&H00FFFFFF,&H78070B15,&H78070B15,-1,0,0,0,100,100,0.6,0,3,12,0,1,64,520,130,1
Style: identity,Segoe UI Semibold,32,&H00FFFFFF,&H00FFFFFF,&H78070B15,&H78070B15,-1,0,0,0,100,100,1.0,0,3,12,0,1,64,520,130,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
`;
  const lines = events.map((event) => (
    `Dialogue: 0,${assTime(event.startSeconds)},${assTime(event.endSeconds)},${event.kind},,0,0,0,,${assText(event.text)}`
  ));
  return `${header}${lines.join("\n")}\n`;
}

function assTime(seconds) {
  const centiseconds = Math.round(seconds * 100);
  const hours = Math.floor(centiseconds / 360000);
  const minutes = Math.floor((centiseconds % 360000) / 6000);
  const secs = Math.floor((centiseconds % 6000) / 100);
  const cs = centiseconds % 100;
  return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${String(cs).padStart(2, "0")}`;
}

function assText(text) {
  return text.replaceAll("\\", "\\\\").replaceAll("{", "\\{").replaceAll("}", "\\}").replaceAll("\n", "\\N");
}
