import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { gzipSync } from "node:zlib";
import { Buffer } from "node:buffer";
import { measureBuildFiles } from "../../scripts/build-size.mjs";

test("build totals sum individual gzip responses, including binary assets", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "build-size-"));
  try {
    const contents = [
      Buffer.from("export default 1;".repeat(100)),
      Buffer.from([0, 255, 10, 80, 32]),
    ];
    const files = contents.map((_, i) => path.join(dir, `asset-${i}`));
    await Promise.all(files.map((file, i) => writeFile(file, contents[i])));
    assert.deepEqual(await measureBuildFiles(files), {
      files: 2,
      bytes: contents.reduce((sum, buffer) => sum + buffer.length, 0),
      compressedBytes: contents.reduce(
        (sum, buffer) => sum + gzipSync(buffer).length,
        0,
      ),
    });
    assert.deepEqual(await measureBuildFiles([]), {
      files: 0,
      bytes: 0,
      compressedBytes: 0,
    });
    await assert.rejects(measureBuildFiles([path.join(dir, "missing.js")]));
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
