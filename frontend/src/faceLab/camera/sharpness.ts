export function laplacianVariance(
  rgba: Uint8ClampedArray,
  w: number,
  h: number,
): number {
  const g = new Float32Array(w * h);
  for (let i = 0; i < w * h; i += 1) {
    g[i] =
      0.299 * rgba[i * 4] + 0.587 * rgba[i * 4 + 1] + 0.114 * rgba[i * 4 + 2];
  }
  let sum = 0;
  let sumSq = 0;
  let n = 0;
  for (let y = 1; y < h - 1; y += 1) {
    for (let x = 1; x < w - 1; x += 1) {
      const i = y * w + x;
      const v = g[i - 1] + g[i + 1] + g[i - w] + g[i + w] - 4 * g[i];
      sum += v;
      sumSq += v * v;
      n += 1;
    }
  }
  return n ? sumSq / n - (sum / n) ** 2 : 0;
}
