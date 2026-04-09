import type { CameraGuidanceContext } from "./types";

export function cameraGuidanceMessage(
  ctx: CameraGuidanceContext,
  requireLiveness: boolean,
): string {
  switch (ctx) {
    case "profile_photo":
      return "Смотрите прямо в камеру.";
    case "bootstrap_front":
      return "Шаг 1 из 3. Смотрите прямо.";
    case "bootstrap_left":
      return "Шаг 2 из 3. Поверните голову чуть влево.";
    case "bootstrap_right":
      return "Шаг 3 из 3. Поверните голову чуть вправо.";
    default:
      return requireLiveness
        ? "Держите лицо в рамке."
        : "Держите лицо в рамке и сделайте снимок.";
  }
}
