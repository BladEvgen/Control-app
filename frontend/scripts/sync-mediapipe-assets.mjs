/**
 * Copies MediaPipe Vision WASM from node_modules into public/ (no runtime CDN).
 * Downloads face_landmarker.task once if missing (install-time only).
 */
import fs from "node:fs";
import path from "node:path";
import https from "node:https";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, "..");

const srcWasm = path.join(root, "node_modules/@mediapipe/tasks-vision/wasm");
const destWasm = path.join(root, "public/mediapipe/tasks-vision/wasm");

const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
const destModel = path.join(root, "public/mediapipe-models/face_landmarker.task");

function copyWasmFiles() {
  if (!fs.existsSync(srcWasm)) {
    console.warn(
      "[sync-mediapipe-assets] skip: @mediapipe/tasks-vision/wasm not found (run npm install).",
    );
    return;
  }
  fs.mkdirSync(destWasm, { recursive: true });
  for (const name of fs.readdirSync(srcWasm)) {
    fs.copyFileSync(path.join(srcWasm, name), path.join(destWasm, name));
  }
  console.log("[sync-mediapipe-assets] wasm →", destWasm);
}

function downloadToFile(url, dest) {
  return new Promise((resolve, reject) => {
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    const file = fs.createWriteStream(dest);
    https
      .get(url, (res) => {
        if (res.statusCode === 301 || res.statusCode === 302) {
          const loc = res.headers.location;
          file.close();
          fs.unlink(dest, () => {});
          if (!loc) {
            reject(new Error("Redirect without Location"));
            return;
          }
          downloadToFile(loc, dest).then(resolve).catch(reject);
          return;
        }
        if (res.statusCode !== 200) {
          file.close();
          fs.unlink(dest, () => {});
          reject(new Error(`GET ${url} → ${res.statusCode}`));
          return;
        }
        res.pipe(file);
        file.on("finish", () => {
          file.close();
          resolve();
        });
      })
      .on("error", (err) => {
        file.close();
        fs.unlink(dest, () => {});
        reject(err);
      });
  });
}

copyWasmFiles();

if (fs.existsSync(destModel)) {
  console.log("[sync-mediapipe-assets] face_landmarker.task already present");
} else {
  console.log("[sync-mediapipe-assets] downloading face_landmarker.task …");
  await downloadToFile(MODEL_URL, destModel);
  console.log("[sync-mediapipe-assets] model →", destModel);
}
