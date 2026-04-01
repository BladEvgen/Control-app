import { spawn } from "node:child_process";
import {
  copyFile,
  mkdir,
  readdir,
  readFile,
  rename,
  rm,
  stat,
  unlink,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const KEEP_RELEASE_COUNT = 5;
const MANIFEST_FILENAME = ".release-manifest.json";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_DIR = path.resolve(__dirname, "..");
const DIST_DIR = path.join(FRONTEND_DIR, "dist");
const DIST_ASSETS_DIR = path.join(DIST_DIR, "assets");
const DIST_TMP_ROOT = path.join(FRONTEND_DIR, "dist-tmp");
const TSC_BIN = path.join(
  FRONTEND_DIR,
  "node_modules",
  "typescript",
  "bin",
  "tsc",
);
const VITE_BIN = path.join(FRONTEND_DIR, "node_modules", "vite", "bin", "vite.js");

const padNumber = (value, size = 2) => String(value).padStart(size, "0");

const formatLocalBuildId = (date) =>
  [
    `${date.getFullYear()}-${padNumber(date.getMonth() + 1)}-${padNumber(date.getDate())}`,
    `${padNumber(date.getHours())}-${padNumber(date.getMinutes())}-${padNumber(date.getSeconds())}_${padNumber(date.getMilliseconds(), 3)}`,
  ].join("_");

const getArgValue = (flagName) => {
  const exactFlag = `--${flagName}`;
  const prefixedFlag = `${exactFlag}=`;

  for (let index = 0; index < process.argv.length; index += 1) {
    const arg = process.argv[index];
    if (arg === exactFlag) {
      return process.argv[index + 1];
    }
    if (arg.startsWith(prefixedFlag)) {
      return arg.slice(prefixedFlag.length);
    }
  }
  return undefined;
};

const runNodeScript = (scriptPath, args, env) =>
  new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [scriptPath, ...args], {
      cwd: FRONTEND_DIR,
      env,
      stdio: "inherit",
    });

    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`${path.basename(scriptPath)} exited with code ${code ?? "unknown"}`));
    });

    child.on("error", reject);
  });

const ensureDir = async (dirPath) => {
  await mkdir(dirPath, { recursive: true });
};

const listFilesRecursive = async (rootDir) => {
  const entries = await readdir(rootDir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const absolutePath = path.join(rootDir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await listFilesRecursive(absolutePath)));
      continue;
    }
    if (entry.isFile()) {
      files.push(absolutePath);
    }
  }

  return files;
};

const copyDirContents = async (sourceDir, targetDir) => {
  const sourceFiles = await listFilesRecursive(sourceDir);
  for (const sourceFile of sourceFiles) {
    const relativePath = path.relative(sourceDir, sourceFile);
    const targetFile = path.join(targetDir, relativePath);
    await ensureDir(path.dirname(targetFile));
    await copyFile(sourceFile, targetFile);
  }
  return sourceFiles.map((filePath) =>
    path.posix.join(
      path.basename(sourceDir),
      path.relative(sourceDir, filePath).split(path.sep).join("/"),
    ),
  );
};

const atomicReplaceFile = async (sourceFile, targetFile) => {
  const tempTarget = `${targetFile}.tmp-${Date.now()}`;
  await copyFile(sourceFile, tempTarget);
  await rename(tempTarget, targetFile);
};

const readJsonIfExists = async (filePath, fallbackValue) => {
  try {
    const contents = await readFile(filePath, "utf-8");
    return JSON.parse(contents);
  } catch (error) {
    if (error && typeof error === "object" && "code" in error && error.code === "ENOENT") {
      return fallbackValue;
    }
    throw error;
  }
};

const writeJsonAtomically = async (filePath, value) => {
  const tempPath = `${filePath}.tmp-${Date.now()}`;
  await writeFile(tempPath, `${JSON.stringify(value, null, 2)}\n`, "utf-8");
  await rename(tempPath, filePath);
};

const pruneEmptyParentDirs = async (filePath, stopDir) => {
  let currentDir = path.dirname(filePath);

  while (currentDir.startsWith(stopDir) && currentDir !== stopDir) {
    const entries = await readdir(currentDir);
    if (entries.length > 0) {
      return;
    }
    await rm(currentDir, { recursive: true, force: true });
    currentDir = path.dirname(currentDir);
  }
};

const cleanupOldAssets = async (manifest) => {
  const keptReleases = manifest.releases.slice(0, KEEP_RELEASE_COUNT);
  const keptAssets = new Set(
    keptReleases.flatMap((entry) => (Array.isArray(entry.assets) ? entry.assets : [])),
  );
  const staleReleases = manifest.releases.slice(KEEP_RELEASE_COUNT);

  for (const release of staleReleases) {
    const releaseAssets = Array.isArray(release.assets) ? release.assets : [];
    for (const assetPath of releaseAssets) {
      if (keptAssets.has(assetPath)) {
        continue;
      }
      const absoluteAssetPath = path.join(DIST_DIR, assetPath);
      await unlink(absoluteAssetPath).catch((error) => {
        if (!(error && typeof error === "object" && "code" in error && error.code === "ENOENT")) {
          throw error;
        }
      });
      await pruneEmptyParentDirs(absoluteAssetPath, DIST_ASSETS_DIR);
    }
  }

  manifest.releases = keptReleases;
};

const main = async () => {
  const mode = getArgValue("mode") ?? "production";
  const now = new Date();
  const buildMeta = {
    buildId: formatLocalBuildId(now),
    builtAtIso: now.toISOString(),
    buildEpochMs: now.getTime(),
  };
  const tempOutDir = path.join(DIST_TMP_ROOT, buildMeta.buildId);
  const manifestPath = path.join(DIST_DIR, MANIFEST_FILENAME);

  const env = {
    ...process.env,
    APP_BUILD_ID: buildMeta.buildId,
    APP_BUILD_TIME_ISO: buildMeta.builtAtIso,
    APP_BUILD_EPOCH_MS: String(buildMeta.buildEpochMs),
  };

  await rm(tempOutDir, { recursive: true, force: true });
  await ensureDir(DIST_TMP_ROOT);
  await ensureDir(DIST_ASSETS_DIR);

  try {
    await runNodeScript(TSC_BIN, ["-p", "tsconfig.json"], env);
    await runNodeScript(
      VITE_BIN,
      ["build", "--mode", mode, "--outDir", tempOutDir],
      env,
    );

    const tempAssetsDir = path.join(tempOutDir, "assets");
    const tempIndexPath = path.join(tempOutDir, "index.html");
    const tempAppVersionPath = path.join(tempOutDir, "app-version.json");
    const tempAssetsStat = await stat(tempAssetsDir);
    if (!tempAssetsStat.isDirectory()) {
      throw new Error(`Build output is missing assets directory: ${tempAssetsDir}`);
    }

    const builtAppVersion = JSON.parse(await readFile(tempAppVersionPath, "utf-8"));
    if (builtAppVersion.buildId !== buildMeta.buildId) {
      throw new Error("Build metadata mismatch between runtime and published app-version.json");
    }

    const assetPaths = await copyDirContents(tempAssetsDir, DIST_ASSETS_DIR);
    await atomicReplaceFile(tempIndexPath, path.join(DIST_DIR, "index.html"));
    await atomicReplaceFile(tempAppVersionPath, path.join(DIST_DIR, "app-version.json"));

    const existingManifest = await readJsonIfExists(manifestPath, { releases: [] });
    const releases = Array.isArray(existingManifest.releases)
      ? existingManifest.releases.filter(
          (entry) =>
            entry &&
            typeof entry === "object" &&
            typeof entry.buildId === "string" &&
            Number.isFinite(entry.buildEpochMs),
        )
      : [];

    const nextManifest = {
      releases: [
        {
          ...buildMeta,
          mode,
          assets: assetPaths,
        },
        ...releases.filter((entry) => entry.buildId !== buildMeta.buildId),
      ].sort((left, right) => Number(right.buildEpochMs) - Number(left.buildEpochMs)),
    };

    await cleanupOldAssets(nextManifest);
    await writeJsonAtomically(manifestPath, nextManifest);
  } finally {
    await rm(tempOutDir, { recursive: true, force: true });
  }
};

main().catch((error) => {
  console.error("[build-release] failed:", error);
  process.exitCode = 1;
});
