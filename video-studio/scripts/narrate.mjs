import {spawnSync} from 'node:child_process';
import {writeFile} from 'node:fs/promises';
import path from 'node:path';
import {generateVoiceJobs} from '../src/browser-tts.mjs';
import {loadCues} from '../src/cues.mjs';
import {validateNarrationMetadata} from '../src/narration.mjs';

const root = process.cwd();
const timeline = await loadCues(path.join(root, 'timeline', 'cues.json'));
const jobs = timeline.scenes.map((scene) => ({
  id: scene.id,
  text: scene.narration.text,
  voice: timeline.voice,
  speed: scene.narration.speed,
  outputPath: path.join(root, 'output', 'audio', 'narration', `${scene.id}.wav`),
}));

await generateVoiceJobs(jobs);

const narration = jobs.map((job) => {
  const probe = spawnSync(
    'ffprobe',
    [
      '-v',
      'error',
      '-show_entries',
      'format=duration',
      '-of',
      'default=nw=1:nk=1',
      job.outputPath,
    ],
    {encoding: 'utf8'},
  );
  if (probe.status !== 0) throw new Error(probe.stderr);
  const scene = timeline.scenes.find((candidate) => candidate.id === job.id);
  return {
    id: job.id,
    file: path.relative(root, job.outputPath).replaceAll('\\', '/'),
    startFrame: scene.narration.startFrame,
    durationFrames: Math.ceil(Number(probe.stdout.trim()) * timeline.fps),
    text: job.text,
  };
});

validateNarrationMetadata(narration, timeline.scenes);
const output = path.join(root, 'output', 'audio', 'narration.json');
await writeFile(output, `${JSON.stringify(narration, null, 2)}\n`);
console.log(`Created ${output}`);
