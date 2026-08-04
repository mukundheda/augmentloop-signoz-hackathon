import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';

const outputDir = path.resolve('output/capture');
await mkdir(outputDir, {recursive: true});

const edge = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const browser = await chromium.launch({headless: true, executablePath: edge});
const context = await browser.newContext({
  viewport: {width: 1280, height: 720},
  recordVideo: {dir: outputDir, size: {width: 1280, height: 720}},
});
const page = await context.newPage();
await page.setContent(`
  <style>
    body { margin: 0; background: #071019; color: white; display: grid;
      place-items: center; height: 100vh; font: 700 64px Arial; }
    span { color: #70d6ff; }
  </style>
  <div>PRODUCT CAPTURE <span>READY</span></div>
`);
await page.waitForTimeout(1200);
const video = page.video();
await context.close();
await video.saveAs(path.join(outputDir, 'playwright-capture.webm'));
await browser.close();
console.log('Playwright capture ready');
