export function visualStateAtFrame(frame, scenes) {
  const scene = scenes.find(
    (candidate) => frame >= candidate.startFrame && frame < candidate.endFrame,
  );
  if (!scene) throw new Error(`frame ${frame} is outside the timeline`);
  return {
    scene,
    progress: (frame - scene.startFrame) / (scene.endFrame - scene.startFrame),
  };
}
