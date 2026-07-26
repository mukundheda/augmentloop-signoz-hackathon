import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { validateAssetManifest } from "../src/assets.mjs";

test("asset manifest requires one music bed and no more than six effects", () => {
  const manifest = {
    licenseUrl: "https://mixkit.co/license/",
    assets: [
      { id: "music-main", kind: "music", title: "Close Up", sourceUrl: "https://mixkit.co/" },
      { id: "sfx-open", kind: "sfx", title: "Software interface start", sourceUrl: "https://mixkit.co/" },
    ],
  };

  assert.doesNotThrow(() => validateAssetManifest(manifest));
});

test("production asset manifest is valid", async () => {
  const manifest = JSON.parse(
    await readFile(new URL("../assets/audio/manifest.json", import.meta.url), "utf8"),
  );
  assert.doesNotThrow(() => validateAssetManifest(manifest));
});

test("asset manifest rejects ambiguous or unlicensed sources", () => {
  assert.throws(
    () => validateAssetManifest({ licenseUrl: "", assets: [] }),
    /licenseUrl/,
  );

  assert.throws(
    () =>
      validateAssetManifest({
        licenseUrl: "https://mixkit.co/license/",
        assets: [
          { id: "music-a", kind: "music", title: "A", sourceUrl: "https://mixkit.co/" },
          { id: "music-b", kind: "music", title: "B", sourceUrl: "https://mixkit.co/" },
        ],
      }),
    /exactly one music/,
  );
});
