import type { FaceVerifyApiResponse } from "./faceLabApi";
import { PadDecisionCard } from "./faceLabPadDiagnostics";
import { padDecisionOf } from "./faceLabPadTypes";
import { pctExact } from "./faceLabDesignTokens";
import { humanizeQualityReasonCodes } from "./faceLabHumanMessages";

function identityMargin(v: FaceVerifyApiResponse) {
  return v.diagnostics?.identity_margin ?? null;
}

function verifyDecision(v: FaceVerifyApiResponse): "YES" | "NO" {
  return v.matched && v.final_decision === "YES" ? "YES" : "NO";
}

function titleForVerify(
  v: FaceVerifyApiResponse,
  decision: "YES" | "NO",
): string {
  if (decision === "YES") return "Лицо подтверждено";
  if (identityMargin(v)?.impostor_ambiguous) return "Слишком похож на другого";
  if (v.status === "LIVENESS_FAIL") return "Фото не принято";
  return "Лицо не подтверждено";
}

function textForVerify(
  v: FaceVerifyApiResponse,
  decision: "YES" | "NO",
): string {
  const summary = (v.summary || "").trim();
  if (decision === "YES") return summary || "Да, можно пропускать.";
  return summary || "Нет, не пропускаем: лицо или фото не прошли проверку.";
}

export function VerifyContractPanel({ v }: { v: FaceVerifyApiResponse }) {
  const decision = verifyDecision(v);
  const live = padDecisionOf(v.liveness.decision, v.liveness.status);
  const qualityReasons = v.quality.passed
    ? null
    : humanizeQualityReasonCodes(v.quality.reason_codes ?? []);

  return (
    <div className="space-y-3">
      <PadDecisionCard
        decision={decision}
        title={titleForVerify(v, decision)}
        text={textForVerify(v, decision)}
      />
      <dl className="flex flex-wrap gap-x-6 gap-y-1 px-1 text-sm text-slate-700 dark:text-slate-300">
        <div className="flex gap-1.5">
          <dt>Сходство:</dt>
          <dd className="font-semibold tabular-nums">
            {pctExact(Math.max(v.score, v.max_cosine))}%
          </dd>
        </div>
        <div className="flex gap-1.5">
          <dt>Живое фото:</dt>
          <dd
            className={`font-semibold ${live === "YES" ? "text-emerald-700 dark:text-emerald-300" : "text-rose-700 dark:text-rose-300"}`}
          >
            {live === "YES" ? "да" : "нет"}
          </dd>
        </div>
      </dl>
      {qualityReasons ? (
        <p className="px-1 text-sm text-amber-800 dark:text-amber-200">
          Что мешает: {qualityReasons}. Снимите ещё раз.
        </p>
      ) : null}
    </div>
  );
}
