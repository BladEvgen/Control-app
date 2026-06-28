import type { CameraGuidanceContext } from "./types";

export function cameraGuidanceMessage(
  ctx: CameraGuidanceContext,
  requireLiveness: boolean,
): string {
  switch (ctx) {
    case "profile_photo":
      return "Лицо по центру. Смотрите прямо.";
    case "bootstrap_front":
      return "Прямой кадр. Смотрите прямо.";
    case "bootstrap_left":
      return "Повернитесь левым ухом к камере. Не наклоняйте голову.";
    case "bootstrap_right":
      return "Повернитесь правым ухом к камере. Не наклоняйте голову.";
    default:
      return requireLiveness
        ? "Держите лицо в рамке."
        : "Держите лицо в рамке и сделайте снимок.";
  }
}
