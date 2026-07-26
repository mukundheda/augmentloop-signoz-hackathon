import {buildAuditionJobs} from '../src/auditions.mjs';
import {generateVoiceJobs} from '../src/browser-tts.mjs';

const text =
  'ToyWorld captures every meaningful learning moment. Gradebook turns those moments into clear, actionable insight.';
const jobs = buildAuditionJobs(text);
await generateVoiceJobs(jobs);
