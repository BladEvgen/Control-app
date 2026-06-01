export type FaceLabTone = "success" | "warning" | "danger" | "info" | "neutral";

const FACE_LAB_EASE_OUT = [0.22, 1, 0.36, 1] as const;

export const faceLabFadeContainer = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.035, delayChildren: 0.015 },
  },
};

export const faceLabFadeItem = {
  hidden: { opacity: 0, y: 8 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.18, ease: FACE_LAB_EASE_OUT },
  },
};

export const faceLabSpring = {
  type: "spring" as const,
  stiffness: 340,
  damping: 28,
  mass: 0.8,
};

export function clamp01(x: number): number {
  return Math.min(1, Math.max(0, x));
}

export function pctExact(x: number): string {
  return (clamp01(x) * 100).toFixed(2);
}

export function pctWidthPercent(x: number): string {
  return `${(clamp01(x) * 100).toFixed(2)}%`;
}

export function faceLabToneShellClass(tone: FaceLabTone): string {
  if (tone === "success") {
    return "border-emerald-200 bg-emerald-50/95 text-emerald-950 dark:border-emerald-800/50 dark:bg-emerald-950/30 dark:text-emerald-50";
  }
  if (tone === "warning") {
    return "border-amber-200 bg-amber-50/95 text-amber-950 dark:border-amber-800/50 dark:bg-amber-950/30 dark:text-amber-50";
  }
  if (tone === "danger") {
    return "border-rose-200 bg-rose-50/95 text-rose-950 dark:border-rose-800/50 dark:bg-rose-950/30 dark:text-rose-50";
  }
  if (tone === "info") {
    return "border-sky-200 bg-sky-50/95 text-sky-950 dark:border-sky-800/50 dark:bg-sky-950/30 dark:text-sky-50";
  }
  return "border-slate-200 bg-white/95 text-slate-950 dark:border-slate-700/70 dark:bg-slate-900/65 dark:text-slate-50";
}

export function faceLabBadgeClass(tone: FaceLabTone): string {
  if (tone === "success") {
    return "border-emerald-200/80 bg-emerald-100 text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-500/15 dark:text-emerald-100";
  }
  if (tone === "warning") {
    return "border-amber-200/80 bg-amber-100 text-amber-900 dark:border-amber-700/50 dark:bg-amber-500/15 dark:text-amber-100";
  }
  if (tone === "danger") {
    return "border-rose-200/80 bg-rose-100 text-rose-800 dark:border-rose-700/50 dark:bg-rose-500/15 dark:text-rose-100";
  }
  if (tone === "info") {
    return "border-sky-200/80 bg-sky-100 text-sky-800 dark:border-sky-700/50 dark:bg-sky-500/15 dark:text-sky-100";
  }
  return "border-slate-200/80 bg-slate-100 text-slate-700 dark:border-slate-700/60 dark:bg-slate-800/90 dark:text-slate-100";
}
