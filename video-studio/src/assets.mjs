const requiredFields = ["id", "kind", "title", "sourceUrl"];

export function validateAssetManifest(manifest) {
  if (!manifest?.licenseUrl) {
    throw new Error("asset manifest requires licenseUrl");
  }
  if (!Array.isArray(manifest.assets)) {
    throw new Error("asset manifest requires assets");
  }

  const music = manifest.assets.filter((asset) => asset.kind === "music");
  const effects = manifest.assets.filter((asset) => asset.kind === "sfx");
  if (music.length !== 1) {
    throw new Error("asset manifest requires exactly one music asset");
  }
  if (effects.length > 6) {
    throw new Error("asset manifest allows no more than six sound effects");
  }

  const ids = new Set();
  for (const asset of manifest.assets) {
    for (const field of requiredFields) {
      if (!asset[field]) throw new Error(`${asset.id ?? "asset"} requires ${field}`);
    }
    if (ids.has(asset.id)) throw new Error(`duplicate asset id: ${asset.id}`);
    ids.add(asset.id);
  }
}
