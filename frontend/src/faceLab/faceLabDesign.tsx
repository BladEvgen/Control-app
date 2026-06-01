import { useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FaChevronDown } from "react-icons/fa";
import {
  faceLabBadgeClass,
  faceLabFadeItem,
  faceLabSpring,
  faceLabToneShellClass,
  pctExact,
  pctWidthPercent,
  type FaceLabTone,
} from "./faceLabDesignTokens";

export function FaceLabBadge({
  tone = "neutral",
  children,
}: {
  tone?: FaceLabTone;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase ${faceLabBadgeClass(tone)}`}
    >
      {children}
    </span>
  );
}

export function FaceLabSurface({
  children,
  className = "",
  tone = "neutral",
  ariaLive,
}: {
  children: ReactNode;
  className?: string;
  tone?: FaceLabTone;
  ariaLive?: "polite" | "assertive";
}) {
  return (
    <motion.section
      className={`rounded-xl border p-4 shadow-sm sm:p-5 ${faceLabToneShellClass(tone)} ${className}`}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={faceLabSpring}
      aria-live={ariaLive}
    >
      {children}
    </motion.section>
  );
}

export function FaceLabSectionHeader({
  eyebrow,
  title,
  detail,
  badge,
}: {
  eyebrow?: string;
  title: string;
  detail?: string;
  badge?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        {eyebrow ? (
          <p className="text-[11px] font-semibold uppercase text-slate-500 dark:text-slate-400">
            {eyebrow}
          </p>
        ) : null}
        <h2 className="mt-1 text-base font-semibold leading-tight text-slate-950 dark:text-slate-50">
          {title}
        </h2>
        {detail ? (
          <p className="mt-1 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
            {detail}
          </p>
        ) : null}
      </div>
      {badge ? <div className="shrink-0">{badge}</div> : null}
    </div>
  );
}

export function FaceLabMetric({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: FaceLabTone;
}) {
  return (
    <div
      className={`rounded-lg border px-3 py-3 ${faceLabToneShellClass(tone)}`}
    >
      <p className="text-[11px] font-semibold uppercase text-slate-500 dark:text-slate-400">
        {label}
      </p>
      <p className="mt-1 text-base font-semibold leading-snug text-slate-950 dark:text-slate-50">
        {value}
      </p>
      {hint ? (
        <p className="mt-1 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function FaceLabBar({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: number;
  tone?: FaceLabTone;
}) {
  const fill =
    tone === "success"
      ? "bg-emerald-500"
      : tone === "warning"
        ? "bg-amber-500"
        : tone === "danger"
          ? "bg-rose-500"
          : tone === "info"
            ? "bg-sky-500"
            : "bg-slate-500";
  return (
    <motion.div className="space-y-2" variants={faceLabFadeItem}>
      <div className="flex items-end justify-between gap-3">
        <span className="text-xs font-medium leading-tight text-slate-600 dark:text-slate-400">
          {label}
        </span>
        <span className="tabular-nums text-lg font-semibold text-slate-950 dark:text-slate-50">
          {pctExact(value)}
          <span className="text-sm text-slate-500 dark:text-slate-400">%</span>
        </span>
      </div>
      <div className="relative h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
        <motion.div
          className={`absolute inset-y-0 left-0 rounded-full ${fill}`}
          initial={{ width: "0%" }}
          animate={{ width: pctWidthPercent(value) }}
          transition={{
            duration: 0.2,
            ease: [0.22, 1, 0.36, 1] as const,
          }}
        />
      </div>
    </motion.div>
  );
}

export function FaceLabDisclosure({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-slate-200/80 pt-2 dark:border-slate-700/70">
      <button
        type="button"
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 rounded-md py-2 text-left text-sm font-semibold text-slate-700 outline-none transition-colors hover:text-slate-950 focus-visible:ring-2 focus-visible:ring-blue-500 dark:text-slate-300 dark:hover:text-slate-50"
        onClick={() => setOpen((v) => !v)}
      >
        <span>{title}</span>
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.16 }}
          aria-hidden
        >
          <FaChevronDown className="h-3.5 w-3.5" />
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{
              duration: 0.18,
              ease: [0.22, 1, 0.36, 1] as const,
            }}
            className="overflow-hidden"
          >
            <div className="pb-2">{children}</div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
