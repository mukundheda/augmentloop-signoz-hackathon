import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {chromium} from 'playwright';
import {buildAuditionJobs} from '../src/auditions.mjs';
import {createVoiceServer} from '../src/voice-server.mjs';

const text =
  'ToyWorld captures every meaningful learning moment. Gradebook turns those moments into clear, actionable insight.';
const jobs = buildAuditionJobs(text);
const server = await createVoiceServer({port: 41903});

try {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  const page = await browser.newPage();
  page.on('console', (message) => console.log(`[browser] ${message.text()}`));
  await page.goto('http://127.0.0.1:41903/voice.html');
  await page.waitForFunction(() => window.kokoroReady);
  await page.evaluate(() => window.kokoroReady);

  for (const job of jobs) {
    const base64 = await page.evaluate(
      (input) => window.generateVoice(input),
      {text: job.text, voice: job.voice},
    );
    await mkdir(path.dirname(job.outputPath), {recursive: true});
    await writeFile(job.outputPath, Buffer.from(base64, 'base64'));
    console.log(`Created ${job.outputPath}`);
  }
  await browser.close();
} finally {
  server.close();
}
