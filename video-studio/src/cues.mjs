import {readFile} from 'node:fs/promises';

export const frameToSeconds = (frame, fps = 30) => frame / fps;

export const validateTimeline = (timeline) => {
  if (timeline.fps !== 30 || timeline.totalFrames !== 1800) {
    throw new Error('Timeline must be exactly 1800 frames at 30 fps');
  }
  if (!Array.isArray(timeline.scenes) || timeline.scenes.length === 0) {
    throw new Error('Timeline must contain scenes');
  }

  const ids = new Set();
  let cursor = 0;
  for (const scene of timeline.scenes) {
    if (ids.has(scene.id)) throw new Error(`Duplicate cue id: ${scene.id}`);
    ids.add(scene.id);
    if (
      !Number.isInteger(scene.startFrame) ||
      !Number.isInteger(scene.endFrame)
    ) {
      throw new Error(`Scene ${scene.id} must use integer frames`);
    }
    if (scene.startFrame !== cursor || scene.endFrame <= scene.startFrame) {
      throw new Error(`Scene ${scene.id} leaves a gap or overlaps`);
    }
    if (!scene.caption?.trim() || !scene.narration?.text?.trim()) {
      throw new Error(`Scene ${scene.id} requires caption and narration`);
    }
    cursor = scene.endFrame;
  }
  if (cursor !== timeline.totalFrames) {
    throw new Error('Scenes must cover the complete timeline');
  }
};

export const loadCues = async (filePath) => {
  const timeline = JSON.parse(await readFile(filePath, 'utf8'));
  validateTimeline(timeline);
  return timeline;
};

export const sceneForFrame = (timeline, frame) => {
  if (!Number.isInteger(frame) || frame < 0 || frame >= timeline.totalFrames) {
    throw new Error(`Frame ${frame} is outside the timeline`);
  }
  const scene = timeline.scenes.find(
    (candidate) =>
      frame >= candidate.startFrame && frame < candidate.endFrame,
  );
  if (!scene) throw new Error(`No scene found for frame ${frame}`);
  return scene;
};
