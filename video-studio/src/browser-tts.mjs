import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {chromium} from 'playwright';
import {createVoiceServer} from './voice-server.mjs';
import {validateVoiceJobs} from './narration.mjs';

export const generateVoiceJobs = async (jobs, {port = 41903} = {}) => {
  validateVoiceJobs(jobs);
  const server = await createVoiceServer({port});
  let browser;
  try {
    browser = await chromium.launch({channel: 'msedge', headless: true});
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${port}/voice.html`);
    await page.waitForFunction(() => window.kokoroReady);
    await page.evaluate(() => window.kokoroReady);

    for (const job of jobs) {
      const base64 = await page.evaluate(
        (input) => window.generateVoice(input),
        {text: job.text, voice: job.voice, speed: job.speed},
      );
      await mkdir(path.dirname(job.outputPath), {recursive: true});
      await writeFile(job.outputPath, Buffer.from(base64, 'base64'));
      console.log(`Created ${job.outputPath}`);
    }
  } finally {
    await browser?.close();
    server.close();
  }
};
