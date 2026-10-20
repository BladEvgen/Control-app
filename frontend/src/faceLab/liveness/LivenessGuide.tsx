import { AnimatePresence, motion } from "framer-motion";
import type { LivenessPhase, LivenessStep } from "./livenessEngine";
import { PHASE_TITLE, STEP_LABEL, poseForPhase } from "./livenessText";
import { PoseGuide, type PoseGuidePose } from "./PoseGuide";

type Props = {
  phase: LivenessPhase;
  hint: string;
  plan: LivenessStep[];
  stepIndex: number;
  progress: number;
  title?: string;
  pose?: PoseGuidePose;
  className?: string;
};

const ease = [0.22, 1, 0.36, 1] as const;

export function LivenessGuide({
  phase,
  hint,
  plan,
  stepIndex,
  progress,
  title,
  pose,
  className = "",
}: Props) {
  const showRail =
    plan.length > 0 && phase !== "unavailable" && phase !== "loading";
  const current = Math.min(stepIndex, plan.length - 1);
  const heading = title ?? PHASE_TITLE[phase];
  const drawn = pose ?? poseForPhase(phase);

  return (
    <div
      className={`flex w-full max-w-md items-center gap-4 rounded-3xl border border-white/15 bg-black/55 p-3 pr-5 text-white shadow-2xl backdrop-blur-xl ${className}`}
    >
      <div className="relative shrink-0 text-white">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={drawn}
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ duration: 0.22, ease }}
          >
            <PoseGuide
              pose={drawn}
              progress={showRail ? (phase === "passed" ? 1 : progress) : null}
              size={84}
            />
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="min-w-0 flex-1">
        {showRail ? (
          <p className="text-[12px] font-medium tabular-nums text-white/65">
            {phase === "passed"
              ? "Все шаги пройдены"
              : `Шаг ${current + 1} из ${plan.length}`}
          </p>
        ) : null}
        <AnimatePresence mode="wait" initial={false}>
          <motion.p
            key={heading}
            className="text-lg font-semibold leading-tight sm:text-xl"
            role="status"
            aria-live="polite"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18, ease }}
          >
            {heading}
          </motion.p>
        </AnimatePresence>
        {hint ? (
          <p className="mt-1 text-sm leading-snug text-white/80">{hint}</p>
        ) : null}

        {showRail ? (
          <ol className="mt-2.5 flex gap-1" aria-label="Шаги проверки">
            {plan.map((step, i) => {
              const done = i < stepIndex;
              const active = i === stepIndex;
              return (
                <li
                  key={step}
                  className="min-w-0 flex-1"
                  aria-current={active ? "step" : undefined}
                >
                  <span className="block h-1.5 overflow-hidden rounded-full bg-white/20">
                    <motion.span
                      className={`block h-full rounded-full ${done ? "bg-emerald-400" : "bg-white"}`}
                      initial={false}
                      animate={{
                        width: done
                          ? "100%"
                          : active
                            ? `${Math.max(8, progress * 100)}%`
                            : "0%",
                      }}
                      transition={{ duration: 0.25, ease }}
                    />
                  </span>
                  <span
                    className={`mt-1 block truncate text-[11px] ${active ? "font-semibold text-white" : done ? "text-white/75" : "text-white/45"}`}
                  >
                    {STEP_LABEL[step]}
                  </span>
                </li>
              );
            })}
          </ol>
        ) : null}
      </div>
    </div>
  );
}
