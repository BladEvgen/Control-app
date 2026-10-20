import { useEffect, type ReactNode } from "react";
import { animate, motion, useMotionValue, useTransform } from "framer-motion";
import {
  faceLabBadgeClass,
  faceLabSpring,
  faceLabToneShellClass,
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

export function AnimatedPercent({
  value,
  decimals = 0,
  className = "",
}: {
  value: number;
  decimals?: number;
  className?: string;
}) {
  const motionValue = useMotionValue(0);
  const rounded = useTransform(motionValue, (v) => v.toFixed(decimals));

  useEffect(() => {
    const controls = animate(motionValue, value, {
      duration: 0.7,
      ease: [0.22, 1, 0.36, 1],
    });
    return () => controls.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return <motion.span className={className}>{rounded}</motion.span>;
}
