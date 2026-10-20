export type LivenessChallenge =
  "blink" | "turn_left" | "turn_right" | "smile" | "mouth_open";

export const LIVENESS_CHALLENGES: readonly LivenessChallenge[] = [
  "blink",
  "turn_left",
  "turn_right",
  "smile",
  "mouth_open",
];
const CHALLENGES_PER_CHECK = 3;
export type LivenessStep = "face" | LivenessChallenge | "hold";
export type LivenessPhase =
  "idle" | "loading" | "unavailable" | LivenessStep | "passed";

export type FacePoint = { x: number; y: number };

export type FaceSignals = {
  landmarks: FacePoint[];
  blendshapes: Record<string, number>;
};

export type LivenessFrame = {
  phase: LivenessStep | "passed";
  hint: string;
  stepIndex: number;
  plan: LivenessStep[];
  progress: number;
};

const NOSE = 1;
const EYE_OUTER_LEFT = 33;
const EYE_OUTER_RIGHT = 263;

const FACE_HOLD_MS = 500;
const FINAL_HOLD_MS = 600;
const LOST_RESET_MS = 900;
const BLINK_MAX_CLOSED_MS = 1200;
const TURN_MIN = 0.3;
const TURN_FRAMES = 2;
const STRAIGHT_MAX = 0.12;
const SMILE_FRAMES = 2;
const FACE_W_MIN = 0.2;
const FACE_W_MAX = 0.8;

export type FaceMeasure = {
  yaw: number;
  centered: boolean;
  tooSmall: boolean;
  tooBig: boolean;
  blink: number;
  smile: number;
  jaw: number;
};

export function measureFace(face: FaceSignals): FaceMeasure | null {
  const lm = face.landmarks;
  if (lm.length <= EYE_OUTER_RIGHT) return null;
  let minX = 1;
  let maxX = 0;
  let minY = 1;
  let maxY = 0;
  for (const p of lm) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  const w = maxX - minX;
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const l = lm[EYE_OUTER_LEFT];
  const r = lm[EYE_OUTER_RIGHT];
  const eyeDist = Math.abs(r.x - l.x) || 1e-6;
  const b = face.blendshapes;
  const avg = (a: string, c: string) => ((b[a] ?? 0) + (b[c] ?? 0)) / 2;
  return {
    yaw: (lm[NOSE].x - (l.x + r.x) / 2) / eyeDist,
    centered: cx > 0.3 && cx < 0.7 && cy > 0.28 && cy < 0.72,
    tooSmall: w < FACE_W_MIN,
    tooBig: w > FACE_W_MAX,
    blink: avg("eyeBlinkLeft", "eyeBlinkRight"),
    smile: avg("mouthSmileLeft", "mouthSmileRight"),
    jaw: b.jawOpen ?? 0,
  };
}

function shuffled<T>(items: T[], random: () => number): T[] {
  const out = items.slice();
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

export function makeLivenessPlan(
  random: () => number = Math.random,
): LivenessStep[] {
  const picked = shuffled([...LIVENESS_CHALLENGES], random).slice(
    0,
    CHALLENGES_PER_CHECK,
  );
  return ["face", ...picked, "hold"];
}

const clamp01 = (x: number) => Math.min(1, Math.max(0, x));

export function createLivenessEngine(random: () => number = Math.random) {
  let plan = makeLivenessPlan(random);
  let index = 0;
  let stepStartedAt = -1;
  let okSince = -1;
  let lostSince = -1;
  let baseBlink = 0;
  let baseSmile = 0;
  let baseJaw = 0;
  let baseFrames = 0;
  let blinkStage: "open" | "closed" = "open";
  let closedAt = 0;
  let blinkOpenSeen = false;
  let turnFrames = 0;
  let turned = false;
  let smileFrames = 0;

  const resetStepState = () => {
    okSince = -1;
    blinkStage = "open";
    blinkOpenSeen = false;
    turnFrames = 0;
    turned = false;
    smileFrames = 0;
  };

  const restart = (newPlan: boolean) => {
    if (newPlan) plan = makeLivenessPlan(random);
    index = 0;
    stepStartedAt = -1;
    lostSince = -1;
    baseBlink = 0;
    baseSmile = 0;
    baseJaw = 0;
    baseFrames = 0;
    resetStepState();
  };

  const frame = (hint: string, progress = 0): LivenessFrame => ({
    phase: index >= plan.length ? "passed" : plan[index],
    hint,
    stepIndex: index,
    plan,
    progress: clamp01(progress),
  });

  const advance = (now: number) => {
    index += 1;
    stepStartedAt = now;
    resetStepState();
  };

  const positionHint = (m: FaceMeasure): string | null => {
    if (m.tooSmall) return "Подойдите ближе к камере.";
    if (m.tooBig) return "Отодвиньтесь немного от камеры.";
    if (!m.centered) return "Поставьте лицо в центр овала.";
    return null;
  };

  function update(face: FaceSignals | null, now: number): LivenessFrame {
    if (index >= plan.length) return frame("Готово, делаем снимок.", 1);
    if (stepStartedAt < 0) stepStartedAt = now;
    const step = plan[index];
    const m = face ? measureFace(face) : null;

    if (!m || !m.centered) {
      if (lostSince < 0) lostSince = now;
      if (index > 0 && now - lostSince >= LOST_RESET_MS) {
        restart(false);
        return frame("Лицо пропало из кадра. Начнём сначала.");
      }
      okSince = -1;
      return frame(
        m
          ? "Поставьте лицо в центр овала."
          : "Не видно лица. Посмотрите в камеру.",
      );
    }
    lostSince = -1;

    if (step === "face") {
      const off =
        positionHint(m) ??
        (Math.abs(m.yaw) > STRAIGHT_MAX ? "Посмотрите прямо в камеру." : null);
      if (off) {
        okSince = -1;
        baseFrames = 0;
        return frame(off);
      }
      if (okSince < 0) okSince = now;
      baseBlink = (baseBlink * baseFrames + m.blink) / (baseFrames + 1);
      baseSmile = (baseSmile * baseFrames + m.smile) / (baseFrames + 1);
      baseJaw = (baseJaw * baseFrames + m.jaw) / (baseFrames + 1);
      baseFrames += 1;
      const p = (now - okSince) / FACE_HOLD_MS;
      if (p >= 1) advance(now);
      return frame("Хорошо, держите лицо в овале.", p);
    }

    if (step === "blink") {
      const closedAbove = Math.max(0.45, baseBlink + 0.3);
      const openBelow = Math.min(0.35, baseBlink + 0.15);
      if (blinkStage === "open") {
        if (m.blink <= openBelow) blinkOpenSeen = true;
        else if (blinkOpenSeen && m.blink >= closedAbove) {
          blinkStage = "closed";
          closedAt = now;
        }
        return frame("Один раз, не спеша: закройте и откройте глаза.", 0);
      }
      if (m.blink <= openBelow) {
        if (now - closedAt <= BLINK_MAX_CLOSED_MS) {
          advance(now);
          return frame("Отлично.", 0);
        }
        blinkStage = "open";
      }
      return frame("Откройте глаза.", 0.6);
    }

    if (step === "turn_left" || step === "turn_right") {
      const sign = step === "turn_left" ? 1 : -1;
      const along = m.yaw * sign;
      const side = step === "turn_left" ? "влево" : "вправо";
      if (!turned) {
        if (along >= TURN_MIN) turnFrames += 1;
        else turnFrames = 0;
        if (turnFrames >= TURN_FRAMES) turned = true;
        if (along <= -TURN_MIN)
          return frame(`Не в ту сторону. Поверните голову ${side}.`, 0);
        return frame(
          "Плавно, примерно на четверть оборота.",
          (along / TURN_MIN) * 0.7,
        );
      }
      if (Math.abs(m.yaw) <= STRAIGHT_MAX) {
        advance(now);
        return frame("Отлично.", 0);
      }
      return frame("Теперь верните голову прямо.", 0.85);
    }

    if (step === "mouth_open") {
      const jawAbove = Math.max(0.35, baseJaw + 0.25);
      if (m.jaw >= jawAbove) smileFrames += 1;
      else smileFrames = 0;
      if (smileFrames >= SMILE_FRAMES) {
        advance(now);
        return frame("Отлично.", 0);
      }
      return frame("Как будто говорите «а».", m.jaw / jawAbove);
    }

    if (step === "smile") {
      const smileAbove = Math.max(0.4, baseSmile + 0.3);
      if (m.smile >= smileAbove) smileFrames += 1;
      else smileFrames = 0;
      if (smileFrames >= SMILE_FRAMES) {
        advance(now);
        return frame("Отлично.", 0);
      }
      return frame("Чуть шире, чем обычно.", m.smile / smileAbove);
    }

    const relaxed =
      m.smile < Math.max(0.3, baseSmile + 0.15) &&
      m.jaw < Math.max(0.25, baseJaw + 0.15);
    const eyesOpen = m.blink < Math.max(0.4, baseBlink + 0.2);
    const off =
      positionHint(m) ??
      (Math.abs(m.yaw) > STRAIGHT_MAX
        ? "Посмотрите прямо в камеру."
        : !relaxed
          ? "Расслабьте лицо."
          : !eyesOpen
            ? "Откройте глаза."
            : null);
    if (off) {
      okSince = -1;
      return frame(off);
    }
    if (okSince < 0) okSince = now;
    const p = (now - okSince) / FINAL_HOLD_MS;
    if (p >= 1) {
      advance(now);
      return frame("Готово, делаем снимок.", 1);
    }
    return frame("Смотрите прямо в камеру, снимок через секунду.", p);
  }

  return {
    update,
    reset: (keepPlan = false) => restart(!keepPlan),
    get plan() {
      return plan;
    },
  };
}

export type LivenessEngine = ReturnType<typeof createLivenessEngine>;
