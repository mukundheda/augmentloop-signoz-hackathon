import test from 'node:test';
import assert from 'node:assert/strict';
import {buildAuditionJobs} from '../src/auditions.mjs';

test('buildAuditionJobs creates four warm female voice candidates', () => {
  const jobs = buildAuditionJobs('Gradebook reveals meaningful progress.');
  assert.deepEqual(
    jobs.map((job) => job.voice),
    ['af_heart', 'af_bella', 'af_nicole', 'af_sarah'],
  );
  assert.ok(jobs.every((job) => job.text.includes('Gradebook')));
  assert.ok(jobs.every((job) => job.outputPath.endsWith('.wav')));
});
