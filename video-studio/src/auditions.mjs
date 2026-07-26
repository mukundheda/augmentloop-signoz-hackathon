import path from 'node:path';

const voices = ['af_heart', 'af_bella', 'af_nicole', 'af_sarah'];

export const buildAuditionJobs = (text, root = process.cwd()) =>
  voices.map((voice) => ({
    voice,
    text,
    outputPath: path.join(
      root,
      'output',
      'audio',
      'auditions',
      `${voice}.wav`,
    ),
  }));
