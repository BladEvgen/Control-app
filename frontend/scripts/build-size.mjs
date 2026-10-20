import { readFile } from "node:fs/promises";
import { promisify } from "node:util";
import { gzip } from "node:zlib";

const compress = promisify(gzip);

export async function measureBuildFiles(files) {
  const sizes = await Promise.all(
    files.map(async (file) => {
      const contents = await readFile(file);
      const compressed = await compress(contents);
      return { bytes: contents.length, compressedBytes: compressed.length };
    }),
  );
  return sizes.reduce(
    (total, size) => ({
      files: total.files + 1,
      bytes: total.bytes + size.bytes,
      compressedBytes: total.compressedBytes + size.compressedBytes,
    }),
    { files: 0, bytes: 0, compressedBytes: 0 },
  );
}
