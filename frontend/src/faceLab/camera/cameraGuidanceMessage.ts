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
      return "Голова чуть влево. Не наклоняйтесь.";
    case "bootstrap_right":
      return "Голова чуть вправо. Не наклоняйтесь.";
    default:
      return requireLiveness
        ? "Держите лицо в рамке."
        : "Держите лицо в рамке и сделайте снимок.";
  }
}
