const allowedOperations = new Set([
  "camera",
  "speed",
  "restart",
  "selectAgent",
  "completeRun",
]);
const allowedCameras = new Set(["overview", "orbit", "top", "chase", "follow"]);

export function buildRecordingPlan(cues) {
  let previousFrame = -1;
  return cues.cameraActions.map((action) => {
    if (!allowedOperations.has(action.operation)) {
      throw new Error(`unsupported recording operation: ${action.operation}`);
    }
    if (action.startFrame < previousFrame) {
      throw new Error("recording actions must be ordered by frame");
    }
    previousFrame = action.startFrame;
    const value = action.operation === "camera" ? action.camera : action.value;
    if (action.operation === "camera" && !allowedCameras.has(value)) {
      throw new Error(`unsupported camera: ${value}`);
    }
    return {
      atFrame: action.startFrame,
      atMs: Math.round((action.startFrame * 1000) / cues.fps),
      operation: action.operation,
      ...(value === undefined ? {} : {value}),
    };
  });
}
