import type { CameraGuidanceContext } from "./types";

export function cameraGuidanceMessage(
  ctx: CameraGuidanceContext,
  requireLiveness: boolean,
): string {
  switch (ctx) {
    case "profile_photo":
      return "Совместите лицо с макетом в светлой рамке на видео — фото для карточки.";
    case "bootstrap_front":
      return "Совместите лицо с макетом головы анфас в светлой рамке на видео.";
    case "bootstrap_left":
      return "Поверните голову влево (~20°): в рамке лицо разворачивается вглубь — не наклон ухом.";
    case "bootstrap_right":
      return "Поверните голову вправо (~20°): в рамке лицо разворачивается вглубь — не наклон ухом.";
    default:
      return requireLiveness
        ? "Встаньте в рамку и следуйте подсказкам — затем сделайте снимок."
        : "Поставьте лицо в рамку и нажмите снимок, когда будете готовы.";
  }
}
