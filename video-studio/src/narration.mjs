export const validateVoiceJobs = (jobs) => {
  const ids = new Set();
  for (const job of jobs) {
    if (!job.text?.trim()) throw new Error(`Voice job ${job.id} has blank text`);
    if (ids.has(job.id)) throw new Error('Voice jobs require unique ids');
    ids.add(job.id);
  }
};

export const validateNarrationMetadata = (narration, scenes) => {
  for (const item of narration) {
    const scene = scenes.find((candidate) => candidate.id === item.id);
    if (!scene) throw new Error(`Narration ${item.id} has no matching scene`);
    if (
      item.startFrame < scene.startFrame ||
      item.startFrame + item.durationFrames > scene.endFrame
    ) {
      throw new Error(`Narration ${item.id} crosses scene boundary`);
    }
  }
};
