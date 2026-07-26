const APPROVED_KINDS = new Set(["chapter", "metric", "identity"]);

export function buildOverlayPlan({fps, overlays}) {
  if (!Number.isFinite(fps) || fps <= 0) throw new Error("fps must be positive");
  return overlays.map((overlay) => {
    if (!APPROVED_KINDS.has(overlay.kind)) {
      throw new Error(`unsupported overlay kind: ${overlay.kind}`);
    }
    if (!overlay.text?.trim()) throw new Error("overlay text must not be blank");
    if (overlay.startFrame < 0 || overlay.endFrame <= overlay.startFrame) {
      throw new Error("overlay frame range must be positive");
    }
    return {
      kind: overlay.kind,
      text: overlay.text.replaceAll("Â·", "/").replaceAll("·", "/"),
      startSeconds: overlay.startFrame / fps,
      endSeconds: overlay.endFrame / fps,
    };
  });
}
