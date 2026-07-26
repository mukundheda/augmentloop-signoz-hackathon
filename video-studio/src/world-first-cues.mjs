import {readFile} from "node:fs/promises";

export const frameToSeconds = (frame, fps) => frame / fps;

export async function loadWorldFirstCues(
  url = new URL("../timeline/world-first-cues.json", import.meta.url),
) {
  const cues = JSON.parse(await readFile(url, "utf8"));
  validateWorldFirstCues(cues);
  return cues;
}

export function validateWorldFirstCues(cues) {
  if (cues.fps !== 30) throw new Error("world-first timeline must use 30 fps");
  if (cues.totalFrames < 3000 || cues.totalFrames > 3600) {
    throw new Error("world-first duration must be between 100 and 120 seconds");
  }

  let cursor = 0;
  for (const chapter of cues.chapters) {
    if (chapter.startFrame !== cursor) throw new Error(`chapter gap before ${chapter.id}`);
    if (chapter.endFrame <= chapter.startFrame) throw new Error(`invalid chapter ${chapter.id}`);
    cursor = chapter.endFrame;
  }
  if (cursor !== cues.totalFrames) throw new Error("chapters must cover the complete film");

  const required = new Set(["orbit", "top", "chase", "follow", "overview"]);
  for (const action of cues.cameraActions) {
    if (action.operation === "camera") required.delete(action.camera);
    if (action.startFrame < 0 || action.startFrame >= cues.totalFrames) {
      throw new Error(`camera action outside timeline at ${action.startFrame}`);
    }
  }
  if (required.size) throw new Error(`missing required cameras: ${[...required].join(", ")}`);

  for (let index = 0; index < cues.narration.length; index += 1) {
    const segment = cues.narration[index];
    if (!segment.text?.trim()) throw new Error(`blank narration segment ${segment.id}`);
    if (segment.startFrame < 0 || segment.endFrame > cues.totalFrames) {
      throw new Error(`narration segment outside timeline: ${segment.id}`);
    }
    if (index > 0) {
      const previous = cues.narration[index - 1];
      if (segment.startFrame - previous.endFrame > 42) {
        throw new Error(`narration gap after ${previous.id} exceeds 42 frames`);
      }
    }
  }
  return cues;
}
