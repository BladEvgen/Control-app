import { useCallback, useEffect, useRef, useState } from "react";
import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";

function mediapipePublicBase(): string {
  const base = import.meta.env.BASE_URL;
  return base.endsWith("/") ? base : `${base}/`;
}

function visionWasmRoot(): string {
  return `${mediapipePublicBase()}mediapipe/tasks-vision/wasm`;
}

function faceLandmarkerModelPath(): string {
  return `${mediapipePublicBase()}mediapipe-models/face_landmarker.task`;
}

const MEDIAPIPE_NATIVE_LOG_RE =
  /OpenGL error checking is disabled|TensorFlow Lite XNNPACK delegate|Graph successfully started running|Graph finished closing successfully|Successfully destroyed WebGL context|gl_context(?:_webgl)?\.cc:\d+|[WIE]\d{4}\s+\d{1,2}:\d{2}:\d{2}/;

function stringifyConsoleArg(a: unknown): string {
  if (typeof a === "string") return a;
  try {
    return String(a);
  } catch {
    return "";
  }
}

function shouldFilterMediapipeNativeLog(args: unknown[]): boolean {
  return MEDIAPIPE_NATIVE_LOG_RE.test(args.map(stringifyConsoleArg).join(" "));
}

function withMediapipeConsoleFilteredSync<T>(fn: () => T): T {
  const origWarn = console.warn.bind(console);
  const origInfo = console.info.bind(console);
  const origLog = console.log.bind(console);
  const wrap =
    (base: (...args: unknown[]) => void) =>
    (...args: unknown[]) => {
      if (shouldFilterMediapipeNativeLog(args)) return;
      base(...args);
    };
  console.warn = wrap(origWarn);
  console.info = wrap(origInfo);
  console.log = wrap(origLog);
  try {
    return fn();
  } finally {
    console.warn = origWarn;
    console.info = origInfo;
    console.log = origLog;
  }
}

async function withMediapipeConsoleFilteredAsync<T>(
  fn: () => Promise<T>,
): Promise<T> {
  const origWarn = console.warn.bind(console);
  const origInfo = console.info.bind(console);
  const origLog = console.log.bind(console);
  const wrap =
    (base: (...args: unknown[]) => void) =>
    (...args: unknown[]) => {
      if (shouldFilterMediapipeNativeLog(args)) return;
      base(...args);
    };
  console.warn = wrap(origWarn);
  console.info = wrap(origInfo);
  console.log = wrap(origLog);
  try {
    return await fn();
  } finally {
    console.warn = origWarn;
    console.info = origInfo;
    console.log = origLog;
  }
}

function closeFaceLandmarker(lm: FaceLandmarker | null): void {
  if (!lm) return;
  withMediapipeConsoleFilteredSync(() => {
    lm.close();
  });
}

let mediapipeConsoleFilterDepth = 0;
let mediapipeConsoleFilterOrig: {
  warn: typeof console.warn;
  info: typeof console.info;
  log: typeof console.log;
} | null = null;

function mediapipeConsoleFilterPush(): void {
  if (mediapipeConsoleFilterDepth++ === 0) {
    mediapipeConsoleFilterOrig = {
      warn: console.warn.bind(console),
      info: console.info.bind(console),
      log: console.log.bind(console),
    };
    const wrap =
      (method: "warn" | "info" | "log") =>
      (...args: unknown[]) => {
        if (shouldFilterMediapipeNativeLog(args)) return;
        const o = mediapipeConsoleFilterOrig;
        if (o) o[method](...args);
      };
    console.warn = wrap("warn");
    console.info = wrap("info");
    console.log = wrap("log");
  }
}

function mediapipeConsoleFilterPop(): void {
  if (mediapipeConsoleFilterDepth <= 0) return;
  mediapipeConsoleFilterDepth -= 1;
  if (mediapipeConsoleFilterDepth > 0) return;
  if (mediapipeConsoleFilterOrig) {
    console.warn = mediapipeConsoleFilterOrig.warn;
    console.info = mediapipeConsoleFilterOrig.info;
    console.log = mediapipeConsoleFilterOrig.log;
    mediapipeConsoleFilterOrig = null;
  }
}

export type LivenessPhase =
  | "idle"
  | "loading"
  | "unavailable"
  | "face"
  | "blink"
  | "yaw"
  | "smile"
  | "passed";

function getBlinkScore(
  blendshapes: { categories?: { categoryName?: string; score?: number }[] }[],
): number {
  const cats = blendshapes?.[0]?.categories;
  if (!cats) return 0;
  let left = 0;
  let right = 0;
  for (const c of cats) {
    const n = c.categoryName ?? "";
    const s = c.score ?? 0;
    if (n === "eyeBlinkLeft") left = s;
    if (n === "eyeBlinkRight") right = s;
  }
  return Math.max(left, right);
}

function getSmileJawScore(
  blendshapes: { categories?: { categoryName?: string; score?: number }[] }[],
): { smile: number; jaw: number } {
  const cats = blendshapes?.[0]?.categories;
  if (!cats) return { smile: 0, jaw: 0 };
  let sl = 0;
  let sr = 0;
  let jaw = 0;
  for (const c of cats) {
    const n = c.categoryName ?? "";
    const s = c.score ?? 0;
    if (n === "mouthSmileLeft") sl = s;
    if (n === "mouthSmileRight") sr = s;
    if (n === "jawOpen") jaw = Math.max(jaw, s);
  }
  return { smile: (sl + sr) / 2, jaw };
}

const NOSE_TIP_IDX = 1;
const DETECT_INTERVAL_MS = 65;
const YAW_MIN_SPAN = 0.045;
const YAW_MEAN_EPS = 0.014;
const YAW_SAMPLES = 40;
const BLINK_OPEN_MAX = 0.26;
const BLINK_PEAK_MIN = 0.42;
const SMILE_COMBO_MAX = 0.14;
const SMILE_COMBO_PEAK_MIN = 0.36;
const SMILE_PEAK_FRAMES = 2;
const SMILE_NEUTRAL_FRAMES = 9;

const HINT_FACE_IN_OVAL =
  "Держите камеру на уровне глаз. Лицо должно целиком находиться в светлом овале на экране. Смотрите прямо в объектив.";

const NOSE_X_MIN = 0.34;
const NOSE_X_MAX = 0.66;
const NOSE_Y_MIN = 0.32;
const NOSE_Y_MAX = 0.68;
const NOSE_STRICT_X_MIN = 0.42;
const NOSE_STRICT_X_MAX = 0.58;
const NOSE_STRICT_Y_MIN = 0.39;
const NOSE_STRICT_Y_MAX = 0.61;
const LEFT_EYE_X = 33;
const RIGHT_EYE_X = 263;
const STRAIGHT_NOSE_EYE_MAX = 0.042;
const FACE_W_MIN = 0.2;
const FACE_H_MIN = 0.24;
const LOST_CENTER_FRAMES = 16;

type LM = { x: number; y: number; z?: number };

function faceGeometry(lm: LM[]) {
  const xs = lm.map((p) => p.x);
  const ys = lm.map((p) => p.y);
  const w = Math.max(...xs) - Math.min(...xs);
  const h = Math.max(...ys) - Math.min(...ys);
  const nose = lm[NOSE_TIP_IDX];
  const inOval =
    nose.x >= NOSE_X_MIN &&
    nose.x <= NOSE_X_MAX &&
    nose.y >= NOSE_Y_MIN &&
    nose.y <= NOSE_Y_MAX;
  const largeEnough = w >= FACE_W_MIN && h >= FACE_H_MIN;
  return { nose, w, h, inOval, largeEnough, ok: inOval && largeEnough };
}

function headStraightEnough(lm: LM[]): boolean {
  if (lm.length <= RIGHT_EYE_X) return false;
  const nose = lm[NOSE_TIP_IDX];
  const midEyes = (lm[LEFT_EYE_X].x + lm[RIGHT_EYE_X].x) / 2;
  return Math.abs(nose.x - midEyes) < STRAIGHT_NOSE_EYE_MAX;
}

function noseInStrictOval(lm: LM[]): boolean {
  const nose = lm[NOSE_TIP_IDX];
  return (
    nose.x >= NOSE_STRICT_X_MIN &&
    nose.x <= NOSE_STRICT_X_MAX &&
    nose.y >= NOSE_STRICT_Y_MIN &&
    nose.y <= NOSE_STRICT_Y_MAX
  );
}

type InternalPhase = "face" | "blink" | "yaw" | "smile" | "passed";

export type UseFaceLivenessOptions = {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  active: boolean;
  skipped: boolean;
};

export type UseFaceLivenessResult = {
  phase: LivenessPhase;
  hint: string;
  allowCapture: boolean;
  isFallback: boolean;
  reset: () => void;
};

export function useFaceLiveness({
  videoRef,
  active,
  skipped,
}: UseFaceLivenessOptions): UseFaceLivenessResult {
  const [phase, setPhase] = useState<LivenessPhase>("idle");
  const [hint, setHint] = useState("");
  const [modelReady, setModelReady] = useState(false);
  const landmarkerRef = useRef<FaceLandmarker | null>(null);
  const rafRef = useRef<number | null>(null);
  const internalRef = useRef<InternalPhase>("face");
  const blinkStageRef = useRef<"need_open" | "need_peak" | "need_open_again">(
    "need_open",
  );
  const smileStageRef = useRef<"need_neutral" | "need_peak">("need_neutral");
  const smilePeakCountRef = useRef(0);
  const smileNeutralStreakRef = useRef(0);
  const noseBufferRef = useRef<number[]>([]);
  const lastDetectMsRef = useRef(0);
  const lostCenterRef = useRef(0);

  const resetInternalToFace = useCallback(() => {
    internalRef.current = "face";
    blinkStageRef.current = "need_open";
    smileStageRef.current = "need_neutral";
    smilePeakCountRef.current = 0;
    smileNeutralStreakRef.current = 0;
    noseBufferRef.current = [];
    lostCenterRef.current = 0;
    setPhase("face");
    setHint(HINT_FACE_IN_OVAL);
  }, []);

  const reset = useCallback(() => {
    resetInternalToFace();
    lastDetectMsRef.current = 0;
    if (skipped) {
      setPhase("passed");
      setHint("");
    } else if (!active) {
      setPhase("idle");
      setHint("");
    } else if (landmarkerRef.current) {
      setPhase("face");
      setHint(HINT_FACE_IN_OVAL);
    } else if (phase === "unavailable") {
      setHint(
        "Проверка здесь недоступна. Можно нажать «Пропустить» и снять кадр вручную.",
      );
    }
  }, [active, skipped, phase, resetInternalToFace]);

  useEffect(() => {
    if (!active) {
      setPhase("idle");
      setHint("");
      setModelReady(false);
      closeFaceLandmarker(landmarkerRef.current);
      landmarkerRef.current = null;
      return;
    }
    if (skipped) {
      closeFaceLandmarker(landmarkerRef.current);
      landmarkerRef.current = null;
      setPhase("passed");
      setHint("");
      setModelReady(false);
      return;
    }

    let cancelled = false;

    (async () => {
      await withMediapipeConsoleFilteredAsync(async () => {
        setPhase("loading");
        setHint("Подождите, загружаем проверку…");
        setModelReady(false);
        try {
          const fileset =
            await FilesetResolver.forVisionTasks(visionWasmRoot());
          if (cancelled) return;

          let lm: FaceLandmarker | null = null;
          try {
            lm = await FaceLandmarker.createFromOptions(fileset, {
              baseOptions: {
                modelAssetPath: faceLandmarkerModelPath(),
                delegate: "GPU",
              },
              runningMode: "VIDEO",
              numFaces: 1,
              outputFaceBlendshapes: true,
            });
          } catch {
            lm = await FaceLandmarker.createFromOptions(fileset, {
              baseOptions: {
                modelAssetPath: faceLandmarkerModelPath(),
              },
              runningMode: "VIDEO",
              numFaces: 1,
              outputFaceBlendshapes: true,
            });
          }

          if (cancelled) {
            closeFaceLandmarker(lm);
            return;
          }
          landmarkerRef.current = lm;
          resetInternalToFace();
          setHint(HINT_FACE_IN_OVAL);
          setModelReady(true);
        } catch {
          if (!cancelled) {
            landmarkerRef.current = null;
            setPhase("unavailable");
            setHint(
              "Не получилось загрузить проверку. Нажмите «Пропустить», чтобы снять кадр вручную.",
            );
            setModelReady(false);
          }
        }
      });
    })();

    return () => {
      cancelled = true;
    };
  }, [active, skipped, resetInternalToFace]);

  useEffect(() => {
    if (!active || skipped || !modelReady) {
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      return;
    }

    const lm = landmarkerRef.current;
    if (!lm) return;

    mediapipeConsoleFilterPush();

    const tick = () => {
      if (!active || skipped) return;

      const video = videoRef.current;
      if (!video || video.readyState < 2) {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }

      const now = performance.now();
      if (now - lastDetectMsRef.current < DETECT_INTERVAL_MS) {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }
      lastDetectMsRef.current = now;

      let result;
      try {
        result = lm.detectForVideo(video, now);
      } catch {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }

      if (internalRef.current === "passed") {
        return;
      }

      const hasFace =
        result.faceLandmarks &&
        result.faceLandmarks.length > 0 &&
        result.faceLandmarks[0].length > RIGHT_EYE_X;

      if (!hasFace) {
        resetInternalToFace();
        setHint("Вас не видно. Подойдите ближе к камере, пожалуйста.");
        rafRef.current = requestAnimationFrame(tick);
        return;
      }

      const landmarks = result.faceLandmarks![0] as LM[];
      const geo = faceGeometry(landmarks);

      if (!geo.ok) {
        lostCenterRef.current += 1;
        if (
          internalRef.current !== "face" &&
          lostCenterRef.current >= LOST_CENTER_FRAMES
        ) {
          resetInternalToFace();
          setHint(
            "Верните лицо в овал на экране, пожалуйста — повторим шаг с начала.",
          );
        } else if (!geo.inOval) {
          setHint("Сдвиньте лицо ближе к центру овала на экране.");
        } else {
          setHint("Подойдите чуть ближе — лицо должно крупнее заполнять овал.");
        }
        rafRef.current = requestAnimationFrame(tick);
        return;
      }
      lostCenterRef.current = 0;

      const blend = result.faceBlendshapes ?? [];
      const blink = getBlinkScore(blend as never);
      const { smile, jaw } = getSmileJawScore(blend as never);
      const smileCombo = Math.max(smile, jaw * 0.85);

      if (internalRef.current === "face") {
        internalRef.current = "blink";
        blinkStageRef.current = "need_open";
        setPhase("blink");
        setHint("Моргните один раз, пожалуйста. Тёмные очки лучше снять.");
      }

      if (internalRef.current === "blink") {
        const stage = blinkStageRef.current;
        if (stage === "need_open") {
          if (blink < BLINK_OPEN_MAX) {
            blinkStageRef.current = "need_peak";
            setHint("Коротко моргните.");
          }
        } else if (stage === "need_peak") {
          if (blink > BLINK_PEAK_MIN) {
            blinkStageRef.current = "need_open_again";
          }
        } else if (stage === "need_open_again") {
          if (blink < BLINK_OPEN_MAX) {
            internalRef.current = "yaw";
            noseBufferRef.current = [];
            setPhase("yaw");
            setHint("Слегка поверните голову в сторону: влево или вправо.");
          }
        }
      }

      if (internalRef.current === "yaw") {
        const nose = landmarks[NOSE_TIP_IDX];
        const buf = noseBufferRef.current;
        buf.push(nose.x);
        if (buf.length > YAW_SAMPLES) buf.shift();
        if (buf.length >= 18) {
          const span = Math.max(...buf) - Math.min(...buf);
          const mean = buf.reduce((a, b) => a + b, 0) / buf.length;
          const hasLeft = buf.some((x) => x < mean - YAW_MEAN_EPS);
          const hasRight = buf.some((x) => x > mean + YAW_MEAN_EPS);
          if (span >= YAW_MIN_SPAN && hasLeft && hasRight) {
            internalRef.current = "smile";
            smileStageRef.current = "need_neutral";
            smilePeakCountRef.current = 0;
            smileNeutralStreakRef.current = 0;
            setPhase("smile");
            setHint(
              "Последний шаг: голова прямо, лицо в центре овала. Сначала спокойное лицо, затем лёгкая улыбка.",
            );
          }
        }
      }

      if (internalRef.current === "smile") {
        const st = smileStageRef.current;
        if (st === "need_neutral") {
          const straight = headStraightEnough(landmarks);
          const centered = noseInStrictOval(landmarks);
          if (!straight || !centered) {
            smileNeutralStreakRef.current = 0;
            if (!straight) {
              setHint("Смотрите прямо в камеру, голову не поворачивайте.");
            } else {
              setHint("Сдвиньте лицо ближе к центру овала на экране.");
            }
          } else if (
            smileCombo < SMILE_COMBO_MAX &&
            blink < BLINK_OPEN_MAX + 0.1
          ) {
            smileNeutralStreakRef.current += 1;
            setHint("Ещё секунду спокойное лицо, без улыбки.");
            if (smileNeutralStreakRef.current >= SMILE_NEUTRAL_FRAMES) {
              smileStageRef.current = "need_peak";
              smileNeutralStreakRef.current = 0;
              setHint("Слегка улыбнитесь или приоткройте рот.");
            }
          } else {
            smileNeutralStreakRef.current = 0;
            setHint("Расслабьте лицо — без улыбки, пожалуйста.");
          }
        } else if (st === "need_peak") {
          if (smileCombo >= SMILE_COMBO_PEAK_MIN) {
            smilePeakCountRef.current += 1;
            if (smilePeakCountRef.current >= SMILE_PEAK_FRAMES) {
              internalRef.current = "passed";
              setPhase("passed");
              setHint("Готово, сохраняем кадр…");
              rafRef.current = null;
              return;
            }
          } else {
            smilePeakCountRef.current = 0;
          }
        }
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      mediapipeConsoleFilterPop();
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [active, skipped, modelReady, videoRef, resetInternalToFace]);

  useEffect(() => {
    return () => {
      closeFaceLandmarker(landmarkerRef.current);
      landmarkerRef.current = null;
    };
  }, []);

  const allowCapture = skipped || phase === "passed";

  const isFallback = phase === "unavailable";

  return {
    phase,
    hint,
    allowCapture,
    isFallback,
    reset,
  };
}
