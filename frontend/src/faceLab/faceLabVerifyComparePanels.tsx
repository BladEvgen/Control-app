import { motion } from "framer-motion";
import type { FaceVerifyApiResponse } from "./faceLabApi";
import { PadDecisionCard } from "./faceLabPadDiagnostics";
import {
  padUiDecisionFromDiagnostics,
  padUiDecisionFromRaw,
} from "./faceLabPadDecision";
import { coercePadDiagnostics, type PadUiDecision } from "./faceLabPadTypes";
import { FaceLabMetric } from "./faceLabDesign";
import { faceLabBadgeClass, pctExact } from "./faceLabDesignTokens";

function identityMargin(v: FaceVerifyApiResponse) {
  return v.diagnostics?.identity_margin ?? null;
}

function verifyDecision(v: FaceVerifyApiResponse): PadUiDecision {
  if (v.matched && v.final_decision === "YES") return "YES";
  if (
    v.status === "QUALITY_FAIL" ||
    v.status === "PAD_ERROR" ||
    v.liveness.status === "insufficient_input_review" ||
    v.liveness.status === "review"
  ) {
    return "REVIEW";
  }
  return "NO";
}

function tone(decision: PadUiDecision): "success" | "warning" | "danger" {
  if (decision === "YES") return "success";
  if (decision === "NO") return "danger";
  return "warning";
}

function titleForVerify(
  v: FaceVerifyApiResponse,
  decision: PadUiDecision,
): string {
  if (decision === "YES") return "Лицо подтверждено";
  if (identityMargin(v)?.impostor_ambiguous) return "Слишком похож на другого";
  if (v.status === "LIVENESS_FAIL") return "Фото не принято";
  if (decision === "REVIEW") return "Система сомневается";
  return "Лицо не подтверждено";
}

function textForVerify(
  v: FaceVerifyApiResponse,
  decision: PadUiDecision,
): string {
  const summary = (v.summary || v.decision_summary || "").trim();
  if (decision === "YES") return summary || "Да, можно пропускать.";
  if (decision === "NO") {
    return summary || "Нет, не пропускаем: лицо или фото не прошли проверку.";
  }
  return summary || "Автоответа недостаточно: нужен новый кадр или оператор.";
}

function livenessDecision(v: FaceVerifyApiResponse): PadUiDecision {
  if (v.liveness.decision) return v.liveness.decision;
  const diag = coercePadDiagnostics(v.liveness.diagnostics);
  if (diag) return padUiDecisionFromDiagnostics(diag);
  return padUiDecisionFromRaw(v.liveness.status, v.liveness.trust_confirmed);
}

function livenessValue(decision: PadUiDecision): string {
  if (decision === "YES") return "да";
  if (decision === "NO") return "нет";
  return "сомневается";
}

export function VerifyContractPanel({ v }: { v: FaceVerifyApiResponse }) {
  const decision = verifyDecision(v);
  const liveness = livenessDecision(v);
  const livenessDisplay = decision === "YES" ? "YES" : liveness;
  const displayScore = Math.max(v.score, v.max_cosine);

  return (
    <motion.div
      className="rounded-xl border border-slate-200 bg-white/95 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/60 sm:p-5"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
    >
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
            Сверка лица
          </h3>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Итог без технических деталей.
          </p>
        </div>
        <span
          className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase ${faceLabBadgeClass(tone(decision))}`}
        >
          {decision === "YES" ? "Да" : decision === "NO" ? "Нет" : "Сомневаюсь"}
        </span>
      </div>

      <PadDecisionCard
        decision={decision}
        title={titleForVerify(v, decision)}
        text={textForVerify(v, decision)}
      />

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <FaceLabMetric
          label="Сходство"
          value={`${pctExact(displayScore)}%`}
          tone={decision === "YES" ? "success" : "neutral"}
        />
        <FaceLabMetric
          label="Фото"
          value={livenessValue(livenessDisplay)}
          tone={
            livenessDisplay === "YES"
              ? "success"
              : livenessDisplay === "NO"
                ? "danger"
                : "warning"
          }
        />
        <FaceLabMetric
          label="Эталоны"
          value={v.gallery_strength === "strong" ? "достаточно" : "мало"}
          tone={v.gallery_strength === "strong" ? "success" : "warning"}
        />
      </div>
    </motion.div>
  );
}
