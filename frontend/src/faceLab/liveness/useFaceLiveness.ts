import { useCallback, useEffect, useRef, useState } from "react";
import type { FaceLandmarker } from "@mediapipe/tasks-vision";
import {
  createLivenessEngine,
  type FaceSignals,
  type FaceView,
  type LivenessPhase,
  type LivenessStep,
} from "./livenessEngine";
import {
  LIVENESS_LOADING_HINT,
  LIVENESS_UNAVAILABLE_HINT,
} from "./livenessText";

function mediapipePublicBase(): string {
  const base = import.meta.env.BASE_URL;
  return base.endsWith("/") ? base : `${base}/`;
}

function assetCandidates(path: string): string[] {
  return Array.from(
    new Set([
      `${mediapipePublicBase()}${path}`,
      `/${path}`,
      `/assets/${path}`,
      `/static/${path}`,
    ]),
  );
}

async function isFetchableAsset(url: string): Promise<boolean> {
  try {
    const head = await fetch(url, { method: "HEAD", cache: "force-cache" });
    if (head.ok) return true;
    if (head.status !== 405) return false;
  } catch {
    return false;
  }
  try {
    return (await fetch(url, { method: "GET", cache: "force-cache" })).ok;
  } catch {
    return false;
  }
}

async function firstFetchableAsset(
  candidates: string[],
  probe: (candidate: string) => string = (candidate) => candidate,
): Promise<string> {
  for (const candidate of candidates) {
    if (await isFetchableAsset(probe(candidate))) return candidate;
  }
  return candidates[0] ?? "";
}

async function resolveMediapipeAssets(): Promise<{
  wasmRoot: string;
  modelPath: string;
}> {
  const [wasmRoot, modelPath] = await Promise.all([
    firstFetchableAsset(
      assetCandidates("mediapipe/tasks-vision/wasm"),
      (root) => `${root.replace(/\/$/, "")}/vision_wasm_internal.wasm`,
    ),
    firstFetchableAsset(
      assetCandidates("mediapipe-models/face_landmarker.task"),
    ),
  ]);
  return { wasmRoot, modelPath };
}

function describeLoadError(error: unknown): string {
  const message =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "";
  const lower = message.toLowerCase();
  if (lower.includes("404") || lower.includes("not found")) {
    return "Не найден файл модели или WASM для проверки движений.";
  }
  if (lower.includes("webgl") || lower.includes("gpu")) {
    return "Браузер не дал включить ускорение для проверки движений.";
  }
  if (lower.includes("wasm"))
    return "Браузер не загрузил WASM-модуль проверки движений.";
  return message.trim() || "Браузер не запустил проверку движений лица.";
}

const MEDIAPIPE_NATIVE_LOG_RE =
  /OpenGL error checking is disabled|TensorFlow Lite XNNPACK delegate|Graph successfully started running|Graph finished closing successfully|Successfully destroyed WebGL context|gl_context(?:_webgl)?\.cc:\d+|[WIE]\d{4}\s+\d{1,2}:\d{2}:\d{2}/;

let filterDepth = 0;
let filterOrig: Pick<Console, "warn" | "info" | "log"> | null = null;

function consoleFilterPush(): void {
  if (filterDepth++ > 0) return;
  const orig = { warn: console.warn, info: console.info, log: console.log };
  filterOrig = orig;
  const wrap =
    (method: "warn" | "info" | "log") =>
    (...args: unknown[]) => {
      if (MEDIAPIPE_NATIVE_LOG_RE.test(args.map((a) => String(a)).join(" ")))
        return;
      orig[method].apply(console, args);
    };
  console.warn = wrap("warn");
  console.info = wrap("info");
  console.log = wrap("log");
}

function consoleFilterPop(): void {
  if (filterDepth <= 0 || --filterDepth > 0 || !filterOrig) return;
  Object.assign(console, filterOrig);
  filterOrig = null;
}

function closeLandmarker(lm: FaceLandmarker | null): void {
  if (!lm) return;
  consoleFilterPush();
  try {
    lm.close();
  } finally {
    consoleFilterPop();
  }
}

const DETECT_INTERVAL_MS = 65;
const DETECT_WIDTH = 480;

export type UseFaceLivenessOptions = {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  active: boolean;
  skipped: boolean;
  onLoadError?: (reason: string, error: unknown) => void;
  view?: FaceView | null;
};

export type FaceLivenessState = {
  phase: LivenessPhase;
  hint: string;
  plan: LivenessStep[];
  stepIndex: number;
  progress: number;
};

export type UseFaceLivenessResult = FaceLivenessState & {
  reset: () => void;
};

const IDLE: FaceLivenessState = {
  phase: "idle",
  hint: "",
  plan: [],
  stepIndex: 0,
  progress: 0,
};

export function useFaceLiveness({
  videoRef,
  active,
  skipped,
  onLoadError,
  view,
}: UseFaceLivenessOptions): UseFaceLivenessResult {
  const [state, setState] = useState<FaceLivenessState>(IDLE);
  const [modelReady, setModelReady] = useState(false);
  const landmarkerRef = useRef<FaceLandmarker | null>(null);
  const engineRef = useRef(createLivenessEngine());
  const onLoadErrorRef = useRef(onLoadError);
  onLoadErrorRef.current = onLoadError;
  const viewRef = useRef(view);
  viewRef.current = view;

  const startEngine = useCallback(() => {
    engineRef.current.reset();
    const f = engineRef.current.update(null, performance.now());
    setState({ ...f, hint: "Посмотрите в камеру, лицо в центре овала." });
  }, []);

  const reset = useCallback(() => {
    if (landmarkerRef.current && active && !skipped) startEngine();
    else engineRef.current.reset();
  }, [active, skipped, startEngine]);

  useEffect(() => {
    if (!active || skipped) {
      closeLandmarker(landmarkerRef.current);
      landmarkerRef.current = null;
      setModelReady(false);
      setState(active ? { ...IDLE, phase: "passed" } : IDLE);
      return;
    }
    let cancelled = false;
    setState({ ...IDLE, phase: "loading", hint: LIVENESS_LOADING_HINT });
    consoleFilterPush();
    void (async () => {
      try {
        const [{ FaceLandmarker, FilesetResolver }, assets] = await Promise.all(
          [import("@mediapipe/tasks-vision"), resolveMediapipeAssets()],
        );
        if (cancelled) return;
        const fileset = await FilesetResolver.forVisionTasks(assets.wasmRoot);
        if (cancelled) return;
        const create = (delegate?: "GPU") =>
          FaceLandmarker.createFromOptions(fileset, {
            baseOptions: { modelAssetPath: assets.modelPath, delegate },
            runningMode: "VIDEO",
            numFaces: 1,
            outputFaceBlendshapes: true,
          });
        const lm = await create("GPU").catch(() => create());
        if (cancelled) {
          closeLandmarker(lm);
          return;
        }
        landmarkerRef.current = lm;
        startEngine();
        setModelReady(true);
      } catch (error: unknown) {
        if (cancelled) return;
        onLoadErrorRef.current?.(describeLoadError(error), error);
        landmarkerRef.current = null;
        setState({
          ...IDLE,
          phase: "unavailable",
          hint: LIVENESS_UNAVAILABLE_HINT,
        });
      } finally {
        consoleFilterPop();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [active, skipped, startEngine]);

  useEffect(() => {
    const lm = landmarkerRef.current;
    if (!active || skipped || !modelReady || !lm) return;
    consoleFilterPush();
    let raf = 0;
    let lastDetect = 0;
    let gap = DETECT_INTERVAL_MS;
    let last: FaceLivenessState | null = null;
    const frame = document.createElement("canvas");
    const frameCtx = frame.getContext("2d", { alpha: false });

    const tick = () => {
      const video = videoRef.current;
      const now = performance.now();
      if (
        !video ||
        !frameCtx ||
        video.readyState < 2 ||
        now - lastDetect < gap
      ) {
        raf = requestAnimationFrame(tick);
        return;
      }
      lastDetect = now;
      let face: FaceSignals | null = null;
      try {
        const h = Math.round(
          (DETECT_WIDTH * video.videoHeight) / video.videoWidth,
        );
        if (frame.width !== DETECT_WIDTH || frame.height !== h) {
          frame.width = DETECT_WIDTH;
          frame.height = h;
        }
        frameCtx.drawImage(video, 0, 0, frame.width, frame.height);
        const result = lm.detectForVideo(frame, now);
        gap = Math.max(DETECT_INTERVAL_MS, (performance.now() - now) * 2);
        const landmarks = result.faceLandmarks?.[0];
        if (landmarks) {
          const blendshapes: Record<string, number> = {};
          for (const c of result.faceBlendshapes?.[0]?.categories ?? []) {
            blendshapes[c.categoryName] = c.score;
          }
          face = { landmarks, blendshapes };
        }
      } catch {
        raf = requestAnimationFrame(tick);
        return;
      }
      const f = engineRef.current.update(
        face,
        now,
        viewRef.current ?? undefined,
      );
      if (
        !last ||
        last.phase !== f.phase ||
        last.hint !== f.hint ||
        last.stepIndex !== f.stepIndex ||
        Math.abs(last.progress - f.progress) >= 0.05
      ) {
        last = f;
        setState(f);
      }
      if (f.phase !== "passed") raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      consoleFilterPop();
    };
  }, [active, skipped, modelReady, videoRef, state.plan]);

  useEffect(() => () => closeLandmarker(landmarkerRef.current), []);

  return { ...state, reset };
}
