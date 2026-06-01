import { motion } from "framer-motion";
import {
  FaCheckCircle,
  FaExclamationTriangle,
  FaTimesCircle,
} from "react-icons/fa";
import { padUiDecisionFromDiagnostics } from "./faceLabPadDecision";
import type { PadDiagnosticsPayload, PadUiDecision } from "./faceLabPadTypes";
import { FaceLabBadge, FaceLabSurface } from "./faceLabDesign";
import type { FaceLabTone } from "./faceLabDesignTokens";

const smoothEase = [0.22, 1, 0.36, 1] as const;

function decisionTone(decision: PadUiDecision): FaceLabTone {
  if (decision === "YES") return "success";
  if (decision === "NO") return "danger";
  return "warning";
}

function decisionLabel(decision: PadUiDecision): string {
  if (decision === "YES") return "Да";
  if (decision === "NO") return "Нет";
  return "Сомневаюсь";
}

function decisionTitle(decision: PadUiDecision): string {
  if (decision === "YES") return "Фото принято";
  if (decision === "NO") return "Фото не принято";
  return "Нужен новый кадр или оператор";
}

function decisionText(decision: PadUiDecision): string {
  if (decision === "YES") {
    return "Можно продолжать проверку лица.";
  }
  if (decision === "NO") {
    return "Не пропускаем: система видит признаки подмены.";
  }
  return "Автоответа недостаточно: переснимите кадр или отдайте оператору.";
}

function DecisionIcon({ decision }: { decision: PadUiDecision }) {
  if (decision === "YES") return <FaCheckCircle className="h-5 w-5" />;
  if (decision === "NO") return <FaTimesCircle className="h-5 w-5" />;
  return <FaExclamationTriangle className="h-5 w-5" />;
}

export function PadDecisionCard({
  decision,
  title,
  text,
}: {
  decision: PadUiDecision;
  title?: string;
  text?: string;
}) {
  const tone = decisionTone(decision);
  return (
    <FaceLabSurface tone={tone} className="overflow-hidden">
      <motion.div
        initial={{ opacity: 0, y: 8, filter: "blur(3px)" }}
        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
        transition={{ duration: 0.24, ease: smoothEase }}
        className="flex items-start gap-3"
      >
        <span className="mt-0.5 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-white/70 text-current shadow-sm dark:bg-white/10">
          <DecisionIcon decision={decision} />
        </span>
        <div className="min-w-0 flex-1">
          <FaceLabBadge tone={tone}>{decisionLabel(decision)}</FaceLabBadge>
          <h3 className="mt-2 text-lg font-semibold leading-tight text-slate-950 dark:text-slate-50">
            {title ?? decisionTitle(decision)}
          </h3>
          <p className="mt-1 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
            {text ?? decisionText(decision)}
          </p>
        </div>
      </motion.div>
    </FaceLabSurface>
  );
}

export function PadDiagnosticsReadout({
  diagnostics,
}: {
  diagnostics: PadDiagnosticsPayload | null;
}) {
  const decision = padUiDecisionFromDiagnostics(diagnostics);
  return <PadDecisionCard decision={decision} />;
}
