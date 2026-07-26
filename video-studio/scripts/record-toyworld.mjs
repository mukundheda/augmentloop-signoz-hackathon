import {spawn} from "node:child_process";
import {mkdir, writeFile} from "node:fs/promises";
import path from "node:path";
import {chromium} from "playwright";
import {buildRecordingPlan} from "../src/recording-plan.mjs";
import {loadWorldFirstCues} from "../src/world-first-cues.mjs";

const root = process.cwd();
const repo = path.resolve(root, "..");
const viewer = path.join(repo, "viewer");
const vite = path.join(viewer, "node_modules", "vite", "bin", "vite.js");
const outputDir = path.join(root, "output", "world-first", "footage");
const output = path.join(outputDir, "toyworld-live.webm");
const port = 41773;
const sourceUrl = `http://127.0.0.1:${port}/`;
const cues = await loadWorldFirstCues();
const plan = buildRecordingPlan(cues);
await mkdir(outputDir, {recursive: true});

const server = spawn(
  process.execPath,
  [vite, "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
  {cwd: viewer, stdio: ["ignore", "pipe", "pipe"]},
);
server.stdout.on("data", (chunk) => process.stdout.write(chunk));
server.stderr.on("data", (chunk) => process.stderr.write(chunk));

async function waitForViewer() {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    try {
      const response = await fetch(sourceUrl);
      if (response.ok) return;
    } catch {
      // Server has not opened its socket yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("ToyWorld viewer did not start");
}

function invokeAction(action) {
  return {
    camera: (api) => api.setCamera(action.value),
    speed: (api) => api.setSpeed(action.value),
    restart: (api) => api.restart(),
    selectAgent: (api) => api.selectFirstActiveAgent(),
    completeRun: (api) => api.completeRun(),
  }[action.operation];
}

let browser;
try {
  await waitForViewer();
  browser = await chromium.launch({channel: "msedge", headless: true});
  const contextCreatedAt = Date.now();
  const context = await browser.newContext({
    viewport: {width: cues.width, height: cues.height},
    recordVideo: {
      dir: outputDir,
      size: {width: cues.width, height: cues.height},
    },
  });
  const page = await context.newPage();
  await page.goto(sourceUrl, {waitUntil: "networkidle"});
  await page.waitForFunction(() => window.toyWorldDemo?.getStatus().state === "RUNNING");
  const video = page.video();
  const readyOffsetMs = Date.now() - contextCreatedAt;
  const scheduleStartedAt = Date.now();
  const actionLog = [];

  for (const action of plan) {
    const remaining = scheduleStartedAt + action.atMs - Date.now();
    if (remaining > 0) await page.waitForTimeout(remaining);
    const result = await page.evaluate(
      ({operation, value}) => {
        const api = window.toyWorldDemo;
        if (!api) throw new Error("ToyWorld demo API unavailable");
        if (operation === "camera") return api.setCamera(value);
        if (operation === "speed") return api.setSpeed(value);
        if (operation === "restart") return api.restart();
        if (operation === "selectAgent") return api.selectFirstActiveAgent();
        if (operation === "completeRun") return api.completeRun();
        throw new Error(`unsupported operation ${operation}`);
      },
      action,
    );
    actionLog.push({...action, executedAtMs: Date.now() - scheduleStartedAt, result});
  }

  const durationMs = Math.round((cues.totalFrames * 1000) / cues.fps);
  const tail = scheduleStartedAt + durationMs - Date.now();
  if (tail > 0) await page.waitForTimeout(tail);
  const finalStatus = await page.evaluate(() => window.toyWorldDemo?.getStatus());
  await context.close();
  await video.saveAs(output);

  await writeFile(
    path.join(outputDir, "recording.json"),
    `${JSON.stringify({
      sourceUrl,
      sourceApp: "viewer",
      width: cues.width,
      height: cues.height,
      fps: cues.fps,
      expectedDurationSeconds: cues.totalFrames / cues.fps,
      readyOffsetSeconds: readyOffsetMs / 1000,
      actions: actionLog,
      finalStatus,
    }, null, 2)}\n`,
  );
  console.log(`Created ${output}`);
} finally {
  await browser?.close();
  server.kill();
}
