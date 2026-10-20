import type { LivenessPhase, LivenessStep } from "./livenessEngine";
import type { PoseGuidePose } from "./PoseGuide";

export const STEP_LABEL: Record<LivenessStep, string> = {
  face: "Лицо",
  blink: "Моргнуть",
  turn_left: "Влево",
  turn_right: "Вправо",
  smile: "Улыбка",
  mouth_open: "Рот",
  hold: "Замереть",
};

export const PHASE_TITLE: Record<LivenessPhase, string> = {
  idle: "Камера выключена",
  loading: "Включаем проверку",
  unavailable: "Снимите вручную",
  face: "Посмотрите в камеру",
  blink: "Моргните",
  turn_left: "Поверните голову влево",
  turn_right: "Поверните голову вправо",
  smile: "Улыбнитесь",
  mouth_open: "Приоткройте рот",
  hold: "Замрите",
  passed: "Готово",
};

export const LIVENESS_LOADING_HINT = "Это займёт пару секунд.";

export const LIVENESS_UNAVAILABLE_HINT =
  "Проверка движений не запустилась в этом браузере. Нажмите кнопку снимка: фото всё равно проверит сервер.";

export function poseForPhase(phase: LivenessPhase): PoseGuidePose {
  if (
    phase === "turn_left" ||
    phase === "turn_right" ||
    phase === "blink" ||
    phase === "smile" ||
    phase === "mouth_open" ||
    phase === "hold"
  ) {
    return phase;
  }
  return phase === "passed" ? "done" : "front";
}
