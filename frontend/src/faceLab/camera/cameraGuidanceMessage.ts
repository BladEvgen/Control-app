import type { CameraGuidanceContext } from "./types";

export function cameraGuidanceMessage(
  ctx: CameraGuidanceContext,
  requireLiveness: boolean,
): string {
  switch (ctx) {
    case "profile_photo":
      return "Лицо в овале, смотрите прямо в камеру. Свет лучше спереди.";
    case "bootstrap_front":
      return "Смотрите прямо в камеру, голову держите ровно.";
    case "bootstrap_left":
      return "Немного поверните голову влево, как на рисунке. Не наклоняйте её.";
    case "bootstrap_right":
      return "Немного поверните голову вправо, как на рисунке. Не наклоняйте её.";
    default:
      return requireLiveness
        ? "Лицо в овале, смотрите прямо в камеру."
        : "Лицо в овале, затем нажмите кнопку снимка.";
  }
}
