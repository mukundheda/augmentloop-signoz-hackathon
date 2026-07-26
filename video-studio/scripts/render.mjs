import {once} from "node:events";
import {spawn} from "node:child_process";
import {createServer} from "node:http";
import {mkdir, readFile} from "node:fs/promises";
import path from "node:path";
import {chromium} from "playwright";

const root = process.cwd();
const cues = JSON.parse(await readFile(path.join(root, "timeline", "cues.json"), "utf8"));
const html = await readFile(path.join(root, "public", "frame.html"));
const cueBytes = Buffer.from(JSON.stringify(cues));
const outputDir = path.join(root, "output");
const output = path.join(outputDir, "gradebook-toyworld-60s.mp4");
const audio = path.join(outputDir, "audio", "master.wav");
const port = 41894;
await mkdir(outputDir, {recursive: true});

const server = createServer((request, response) => {
  if (request.url?.startsWith("/timeline/cues.json")) {
    response.writeHead(200, {"Content-Type": "application/json"});
    response.end(cueBytes);
  } else {
    response.writeHead(200, {"Content-Type": "text/html; charset=utf-8"});
    response.end(html);
  }
});
await new Promise((resolve) => server.listen(port, "127.0.0.1", resolve));

const ffmpeg = spawn(
  "ffmpeg",
  [
    "-y", "-f", "image2pipe", "-framerate", String(cues.fps), "-vcodec", "mjpeg", "-i", "pipe:0",
    "-i", audio,
    "-map", "0:v:0", "-map", "1:a:0",
    "-frames:v", String(cues.totalFrames),
    "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-profile:v", "high",
    "-pix_fmt", "yuv420p", "-r", String(cues.fps),
    "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
    "-t", "60", "-movflags", "+faststart", output,
  ],
  {stdio: ["pipe", "inherit", "inherit"]},
);
const ffmpegDone = once(ffmpeg, "close");

try {
  const browser = await chromium.launch({channel: "msedge", headless: true});
  const page = await browser.newPage({
    viewport: {width: cues.width, height: cues.height},
    deviceScaleFactor: 1,
  });
  await page.goto(`http://127.0.0.1:${port}/?frame=0`, {waitUntil: "networkidle"});
  await page.evaluate(() => document.fonts.ready);

  for (let frame = 0; frame < cues.totalFrames; frame += 1) {
    if (frame > 0) await page.evaluate((value) => window.renderFrame(value), frame);
    const image = await page.screenshot({type: "jpeg", quality: 95});
    if (!ffmpeg.stdin.write(image)) await once(ffmpeg.stdin, "drain");
    if ((frame + 1) % 60 === 0) {
      process.stdout.write(`Rendered ${frame + 1}/${cues.totalFrames} frames\n`);
    }
  }
  ffmpeg.stdin.end();
  await browser.close();
} finally {
  server.close();
}

const [code] = await ffmpegDone;
if (code !== 0) throw new Error(`FFmpeg exited with ${code}`);
console.log(`Created ${output}`);
