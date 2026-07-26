import {spawn} from "node:child_process";
import {mkdir} from "node:fs/promises";
import path from "node:path";
import {chromium} from "playwright";

const root = process.cwd();
const output = path.join(root, "output", "review");
await mkdir(output, {recursive: true});
const server = spawn(process.execPath, ["scripts/preview.mjs"], {stdio: "ignore"});

try {
  const browser = await chromium.launch({channel: "msedge", headless: true});
  const page = await browser.newPage({viewport: {width: 1920, height: 1080}});
  for (const frame of [90, 320, 720, 1180, 1550, 1740]) {
    await page.goto(`http://127.0.0.1:41893/?frame=${frame}`, {waitUntil: "networkidle"});
    await page.screenshot({path: path.join(output, `frame-${frame}.png`)});
  }
  await browser.close();
} finally {
  server.kill();
}

console.log(`Created review frames in ${output}`);
