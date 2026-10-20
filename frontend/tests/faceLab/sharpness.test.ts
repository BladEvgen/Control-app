import test from "node:test";
import assert from "node:assert/strict";
import { laplacianVariance } from "../../src/faceLab/camera/sharpness.ts";

function image(w: number, h: number, px: (x: number, y: number) => number) {
  const rgba = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++)
      rgba.fill(px(x, y), (y * w + x) * 4, (y * w + x) * 4 + 3);
  return rgba;
}

test("sharp edges score higher than the same scene blurred, flat scores zero", () => {
  const sharp = image(32, 32, (x) => (x % 8 < 4 ? 0 : 255));
  const blurred = image(
    32,
    32,
    (x) => 128 + 127 * Math.sin((x / 8) * 2 * Math.PI),
  );
  const flat = image(32, 32, () => 90);
  assert.ok(
    laplacianVariance(sharp, 32, 32) > laplacianVariance(blurred, 32, 32),
  );
  assert.equal(laplacianVariance(flat, 32, 32), 0);
});
