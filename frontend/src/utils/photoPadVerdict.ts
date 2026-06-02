import type { PhotoData, PhotoSpoofStatus } from "../schemas/IData";

export type PhotoPadVerdictVariant =
  | "clean"
  | "review"
  | "suspicious"
  | "error"
  | "pending";

export type PhotoPadVerdictDisplay = {
  variant: PhotoPadVerdictVariant;
  headline: string;
  summary: string;
  riskPercent: number | null;
  manualOverride: "clean" | "suspicious" | null;
};

const PAD_UI_REASON_PREFIX = "pad_ui_reason:";

const HEADLINE: Record<PhotoPadVerdictVariant, string> = {
  clean: "Нормально",
  review: "Нужна проверка",
  suspicious: "Подмена вероятна",
  error: "Ошибка проверки",
  pending: "Проверяется…",
};

const FALLBACK_SUMMARY: Record<PhotoPadVerdictVariant, string> = {
  clean: "Подмена не подтверждена.",
  review: "Посмотрите кадр вручную.",
  suspicious: "Признаки подмены согласованы.",
  error: "Автопроверка не завершилась.",
  pending: "Ожидается результат.",
};

const shortenSummary = (text: string): string => {
  let s = text.trim();
  const firstSentence = s.split(/(?<=[.!?])\s+/)[0] ?? s;
  s = firstSentence.replace(/\s*\([^)]*\)/g, "").replace(/\s+/g, " ").trim();
  if (s.length > 120) {
    s = `${s.slice(0, 117).trim()}…`;
  }
  return s;
};

const extractUiReason = (tags: string[]): string | null => {
  for (const raw of tags) {
    if (raw.startsWith(PAD_UI_REASON_PREFIX)) {
      return raw.slice(PAD_UI_REASON_PREFIX.length).trim();
    }
  }
  return null;
};

const normalizeTags = (
  value: PhotoData["photoSpoofTags"] | undefined,
): string[] => {
  if (!Array.isArray(value)) return [];
  return value.filter((t): t is string => typeof t === "string");
};

const riskPercentFromPhoto = (photo: Partial<PhotoData>): number | null => {
  if (
    typeof photo.photoSpoofScore !== "number" ||
    !Number.isFinite(photo.photoSpoofScore)
  ) {
    return null;
  }
  return Math.round(Math.max(0, Math.min(1, photo.photoSpoofScore)) * 100);
};

export const resolvePhotoPadVariant = (
  status: PhotoSpoofStatus,
): PhotoPadVerdictVariant => {
  if (status === "suspicious") return "suspicious";
  if (status === "review" || status === "pending") return "review";
  if (status === "error") return "error";
  return "clean";
};

export const buildPhotoPadVerdictDisplay = (
  photo: Partial<PhotoData>,
  effectiveStatus: PhotoSpoofStatus,
): PhotoPadVerdictDisplay => {
  const tags = normalizeTags(photo.photoSpoofTags);
  const manual = photo.photoManualVerdict ?? "none";
  const manualOverride =
    manual === "clean" || manual === "suspicious" ? manual : null;

  let variant = resolvePhotoPadVariant(effectiveStatus);
  if (manualOverride === "suspicious") variant = "suspicious";
  if (manualOverride === "clean") variant = "clean";

  let headline = HEADLINE[variant];
  if (manualOverride === "suspicious") headline = "Подозрительное (вручную)";
  if (manualOverride === "clean") headline = "Нормально (вручную)";

  const raw = extractUiReason(tags) || FALLBACK_SUMMARY[variant];
  const summary = shortenSummary(raw);

  return {
    variant,
    headline,
    summary,
    riskPercent: riskPercentFromPhoto(photo),
    manualOverride,
  };
};

export const photoPadVerdictPanelClass = (
  variant: PhotoPadVerdictVariant,
): string => {
  switch (variant) {
    case "suspicious":
      return "border-rose-200/90 bg-rose-50/80 dark:border-rose-500/30 dark:bg-rose-950/35";
    case "review":
      return "border-amber-200/90 bg-amber-50/80 dark:border-amber-500/30 dark:bg-amber-950/30";
    case "error":
      return "border-orange-200/90 bg-orange-50/80 dark:border-orange-500/30 dark:bg-orange-950/30";
    case "pending":
      return "border-slate-200/90 bg-slate-50/90 dark:border-slate-600/60 dark:bg-slate-900/60";
    default:
      return "border-emerald-200/90 bg-emerald-50/70 dark:border-emerald-500/25 dark:bg-emerald-950/25";
  }
};

export const photoPadVerdictRiskClass = (
  variant: PhotoPadVerdictVariant,
): string => {
  switch (variant) {
    case "suspicious":
      return "text-rose-700 dark:text-rose-200";
    case "review":
      return "text-amber-800 dark:text-amber-200";
    case "error":
      return "text-orange-700 dark:text-orange-200";
    default:
      return "text-emerald-700 dark:text-emerald-200";
  }
};
