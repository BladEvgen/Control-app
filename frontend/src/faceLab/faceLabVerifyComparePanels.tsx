import { useState, type Dispatch, type SetStateAction } from "react";
import { motion } from "framer-motion";
import type { FaceVerifyApiResponse } from "./faceLabApi";
import { formatServerElapsed } from "./faceLabFormat";
import { PadDiagnosticsReadout } from "./faceLabPadDiagnostics";
import { coercePadDiagnostics } from "./faceLabPadTypes";
import {
  humanizeFaceVerifyStatus,
  humanizePadStatus,
  humanizePadTag,
  humanizeVerifyReasonCode,
} from "./faceLabHumanMessages";

const fadeContainer = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.045, delayChildren: 0.02 },
  },
};

const fadeItem = {
  hidden: { opacity: 0, y: 8 },
  show: {
    opacity: 1,
    y: 0,
    transition: { type: "spring" as const, stiffness: 380, damping: 28 },
  },
};

function clamp01(x: number): number {
  return Math.min(1, Math.max(0, x));
}

function pctExact(x: number): string {
  return (clamp01(x) * 100).toFixed(2);
}

function pctWidthPercent(x: number): string {
  return `${(clamp01(x) * 100).toFixed(2)}%`;
}

const springBar: {
  type: "spring";
  stiffness: number;
  damping: number;
  mass: number;
} = {
  type: "spring",
  stiffness: 420,
  damping: 26,
  mass: 0.78,
};

function Bar({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "emerald" | "amber" | "slate" | "rose";
}) {
  const pctStr = pctExact(value);
  const bg =
    tone === "emerald"
      ? "bg-emerald-500/85"
      : tone === "amber"
        ? "bg-amber-500/85"
        : tone === "rose"
          ? "bg-rose-500/85"
          : "bg-slate-500/80";
  return (
    <motion.div className="space-y-2" variants={fadeItem}>
      <div className="flex items-end justify-between gap-3">
        <span className="text-xs font-medium leading-tight text-slate-600 dark:text-slate-400">
          {label}
        </span>
        <span className="tabular-nums text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-50">
          {pctStr}
          <span className="text-sm font-semibold text-slate-500 dark:text-slate-400">
            %
          </span>
        </span>
      </div>
      <div className="relative h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
        <motion.div
          className={`absolute inset-y-0 left-0 rounded-full ${bg}`}
          initial={{ width: "0%" }}
          animate={{ width: pctWidthPercent(value) }}
          transition={springBar}
        />
      </div>
    </motion.div>
  );
}

function galleryStrengthLine(
  g: FaceVerifyApiResponse["gallery_strength"],
): string {
  if (g === "strong") return "Галерея надёжная.";
  return "Галерея небольшая, поэтому порог строже.";
}

function outcomeBadgeClass(tone: "success" | "warning" | "danger"): string {
  if (tone === "success") {
    return "border-emerald-200/80 bg-emerald-50 text-emerald-800 dark:border-emerald-800/40 dark:bg-emerald-500/15 dark:text-emerald-200";
  }
  if (tone === "warning") {
    return "border-amber-200/80 bg-amber-50 text-amber-900 dark:border-amber-800/40 dark:bg-amber-500/15 dark:text-amber-100";
  }
  return "border-rose-200/80 bg-rose-50 text-rose-800 dark:border-rose-800/40 dark:bg-rose-500/15 dark:text-rose-200";
}

function evidenceTileClass(
  tone: "success" | "warning" | "danger" | "neutral" = "neutral",
): string {
  if (tone === "success") {
    return "border-emerald-200/80 bg-emerald-50/80 dark:border-emerald-800/40 dark:bg-emerald-500/10";
  }
  if (tone === "warning") {
    return "border-amber-200/80 bg-amber-50/80 dark:border-amber-800/40 dark:bg-amber-500/10";
  }
  if (tone === "danger") {
    return "border-rose-200/80 bg-rose-50/80 dark:border-rose-800/40 dark:bg-rose-500/10";
  }
  return "border-slate-200/80 bg-slate-50/80 dark:border-slate-700/60 dark:bg-slate-950/40";
}

function verifyVerdictLabel(v: FaceVerifyApiResponse, yes: boolean): string {
  if (
    yes &&
    (v.liveness.status === "insufficient_input_review" ||
      v.liveness.status === "review")
  ) {
    return "Совпало, но кадр слабый";
  }
  if (yes) return "Совпадение подтверждено";
  if (v.status === "QUALITY_FAIL") return "Кадр слабый для сравнения";
  if (v.status === "LIVENESS_FAIL") return "Кадр не прошёл проверку фото";
  if (v.status === "PAD_ERROR") return "Проверка фото не завершилась";
  return "Совпадение не подтверждено";
}

function verifyVerdictTone(
  v: FaceVerifyApiResponse,
  yes: boolean,
): "success" | "warning" | "danger" {
  if (
    yes &&
    (v.liveness.status === "insufficient_input_review" ||
      v.liveness.status === "review")
  ) {
    return "warning";
  }
  if (yes) return "success";
  if (
    v.status === "QUALITY_FAIL" ||
    v.status === "PAD_ERROR" ||
    v.liveness.status === "insufficient_input_review"
  ) {
    return "warning";
  }
  return "danger";
}

function livenessValue(v: FaceVerifyApiResponse): string {
  if (v.status === "PAD_ERROR") return "нет ответа";
  if (
    v.matched &&
    v.final_decision === "YES" &&
    (v.liveness.status === "insufficient_input_review" ||
      v.liveness.status === "review")
  ) {
    return "нужен кадр лучше";
  }
  if (v.liveness.status === "insufficient_input_review") return "мало данных";
  if (
    v.liveness.checked &&
    v.liveness.trust_confirmed === true &&
    v.liveness.status === "clean"
  ) {
    return "подтверждена";
  }
  if (v.liveness.checked) return "не подтверждена";
  return "не проверена";
}

function buildVerifyUncertaintyLines(v: FaceVerifyApiResponse): string[] {
  const lines: string[] = [];
  const seen = new Set<string>();
  const push = (line: string | null | undefined) => {
    const text = (line ?? "").trim();
    if (!text || seen.has(text)) return;
    seen.add(text);
    lines.push(text);
  };

  if (!v.quality.passed) {
    push("Кадр слабый для уверенного сравнения.");
  }
  if (v.liveness.status === "insufficient_input_review") {
    push("Для проверки фото системе не хватило пригодного изображения.");
  }
  if (v.gallery_strength === "weak") {
    push("Эталонов мало, поэтому порог сравнения строже.");
  }
  for (const code of v.reason_codes.slice(0, 3)) {
    push(humanizeVerifyReasonCode(code));
  }
  return lines;
}

function EvidenceTile({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "success" | "warning" | "danger" | "neutral";
}) {
  return (
    <div
      className={`rounded-xl border px-3 py-3 shadow-sm transition-colors ${evidenceTileClass(tone)}`}
    >
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </p>
      <p className="mt-1 text-base font-semibold leading-snug text-slate-900 dark:text-slate-100">
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

function VerifyPadLivenessDetails({
  liveness,
  padBarsOpen,
  setPadBarsOpen,
}: {
  liveness: FaceVerifyApiResponse["liveness"];
  padBarsOpen: boolean;
  setPadBarsOpen: Dispatch<SetStateAction<boolean>>;
}) {
  const padDiag = coercePadDiagnostics(liveness.diagnostics);
  return (
    <>
      {padDiag ? (
        <PadDiagnosticsReadout diagnostics={padDiag} />
      ) : typeof liveness.status === "string" ? (
        <p className="mb-2 text-slate-600 dark:text-slate-400">
          {humanizePadStatus(liveness.status)}
        </p>
      ) : null}
      <div className="mt-2">
        <button
          type="button"
          className="text-xs font-medium text-blue-600 underline-offset-2 hover:underline dark:text-blue-400"
          aria-expanded={padBarsOpen}
          onClick={() => setPadBarsOpen((x) => !x)}
        >
          {padBarsOpen
            ? "Скрыть числовые сигналы проверки фото"
            : "Показать числовые сигналы проверки фото"}
        </button>
      </div>
      {padBarsOpen &&
      typeof liveness.risk_score === "number" &&
      typeof liveness.deepface_score === "number" ? (
        <motion.div
          className="mt-2 space-y-2"
          variants={fadeContainer}
          initial="hidden"
          animate="show"
        >
          <Bar
            label="Риск подмены"
            value={liveness.risk_score}
            tone={
              liveness.risk_score > 0.45
                ? "rose"
                : liveness.risk_score > 0.25
                  ? "amber"
                  : "emerald"
            }
          />
          <Bar
            label="Подлинность лица (FasNet)"
            value={liveness.deepface_score}
            tone="slate"
          />
          {typeof liveness.device_score === "number" ? (
            <Bar
              label="Устройство у лица"
              value={liveness.device_score}
              tone="slate"
            />
          ) : null}
          {typeof liveness.device_bg_score === "number" ? (
            <Bar
              label="Устройство (фон)"
              value={liveness.device_bg_score}
              tone="slate"
            />
          ) : null}
          {typeof liveness.frame_score === "number" ? (
            <Bar
              label="Рамка у лица"
              value={liveness.frame_score}
              tone="slate"
            />
          ) : null}
          {typeof liveness.frame_global_score === "number" ? (
            <Bar
              label="Рамка (глоб.)"
              value={liveness.frame_global_score}
              tone="slate"
            />
          ) : null}
          {typeof liveness.recapture_score === "number" ? (
            <Bar
              label="Рекапчер (лицо)"
              value={liveness.recapture_score}
              tone="slate"
            />
          ) : null}
          {typeof liveness.quality_penalty === "number" ? (
            <Bar
              label="Штраф за качество"
              value={liveness.quality_penalty}
              tone="amber"
            />
          ) : null}
        </motion.div>
      ) : null}
      {!padDiag && liveness.tags && liveness.tags.length > 0 ? (
        <div className="mt-2">
          <p className="mb-1 text-[11px] font-medium text-slate-500">
            Служебные пометки
          </p>
          <div className="flex flex-wrap gap-1">
            {liveness.tags.map((tag) => (
              <span
                key={tag}
                className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[11px] text-slate-600 dark:border-slate-600 dark:bg-slate-950/80 dark:text-slate-300"
              >
                {humanizePadTag(tag)}
              </span>
            ))}
          </div>
        </div>
      ) : null}
      {!padDiag &&
      typeof liveness.elapsed_ms === "number" &&
      typeof liveness.model_version === "string" ? (
        <p className="mt-2 tabular-nums text-[11px] text-slate-500">
          {liveness.model_version} · {formatServerElapsed(liveness.elapsed_ms)}{" "}
          ({liveness.elapsed_ms.toFixed(0)} мс)
        </p>
      ) : null}
    </>
  );
}

function livenessSummary(v: FaceVerifyApiResponse): string {
  if (v.status === "PAD_ERROR") return "Проверка фото не завершилась.";
  if (v.status === "LIVENESS_FAIL") return "Проверка фото не подтверждена.";
  if (
    v.matched &&
    v.final_decision === "YES" &&
    (v.liveness.status === "insufficient_input_review" ||
      v.liveness.status === "review")
  ) {
    return "Сходство посчитано, но для уверенного кадра лучше переснять фото.";
  }
  if (v.liveness.status === "insufficient_input_review") {
    return "Для проверки фото не хватило качества кадра.";
  }
  if (
    v.liveness.checked &&
    v.liveness.trust_confirmed === true &&
    v.liveness.status === "clean"
  ) {
    return "Проверка фото пройдена.";
  }
  if (v.liveness.checked) return "Проверка фото не подтверждена.";
  return "Результат проверки фото отсутствует.";
}

export function VerifyContractPanel({ v }: { v: FaceVerifyApiResponse }) {
  const [open, setOpen] = useState(false);
  const [padBarsOpen, setPadBarsOpen] = useState(false);
  const yes = v.matched && v.final_decision === "YES";
  const displayScore = Math.max(v.score, v.max_cosine);
  const verdictTone = verifyVerdictTone(v, yes);
  const verdictLabel = verifyVerdictLabel(v, yes);
  const shortReason = (
    v.summary ||
    v.decision_summary ||
    humanizeVerifyReasonCode(v.reason_codes[0] ?? "")
  ).trim();
  const uncertaintyLines = buildVerifyUncertaintyLines(v);
  const qualityHint =
    typeof v.quality.face_area_ratio === "number"
      ? `Лицо занимает ${(v.quality.face_area_ratio * 100).toFixed(2)}% кадра.`
      : undefined;

  return (
    <motion.div
      className="rounded-xl border border-slate-200 bg-white/95 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/60 sm:p-5"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
    >
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
            Сравнение с эталоном
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Короткий итог по сверке лица.
          </p>
        </div>
        <span
          className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide ${outcomeBadgeClass(verdictTone)}`}
        >
          {verdictLabel}
        </span>
      </div>

      <div className="mb-4 rounded-2xl border border-slate-200/80 bg-gradient-to-br from-slate-50/95 via-white to-slate-50/80 p-4 shadow-sm dark:border-slate-700/60 dark:from-slate-950/90 dark:via-slate-900/75 dark:to-slate-950/80">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Причина
        </p>
        <p className="mt-1 text-base font-semibold leading-snug text-slate-900 dark:text-slate-100">
          {shortReason || "Сравнение завершено."}
        </p>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <EvidenceTile
          label="Сходство"
          value={`${pctExact(displayScore)}%`}
          hint={`Порог для этого кадра: ${pctExact(v.threshold_applied)}%`}
          tone={yes ? "success" : "neutral"}
        />
        <EvidenceTile
          label="Проверка фото"
          value={livenessValue(v)}
          hint={livenessSummary(v)}
          tone={
            v.liveness.status === "insufficient_input_review"
              ? "warning"
              : yes
                ? "success"
                : v.status === "LIVENESS_FAIL"
                  ? "danger"
                  : "neutral"
          }
        />
        <EvidenceTile
          label="Галерея"
          value={v.gallery_strength === "strong" ? "надёжная" : "строгий режим"}
          hint={`${galleryStrengthLine(v.gallery_strength)} ${v.gallery_size} эталонов · ${v.gallery.distinct_enrollment_sources} источника`}
          tone={v.gallery_strength === "strong" ? "success" : "warning"}
        />
        <EvidenceTile
          label="Качество"
          value={v.quality.passed ? "достаточно" : "с ограничениями"}
          hint={qualityHint}
          tone={v.quality.passed ? "neutral" : "warning"}
        />
      </div>

      {uncertaintyLines.length > 0 ? (
        <div className="mb-4 rounded-2xl border border-amber-200/80 bg-amber-50/80 p-4 shadow-sm dark:border-amber-800/40 dark:bg-amber-500/10">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-900 dark:text-amber-100">
            Неопределённость
          </p>
          <ul className="mt-2 space-y-1.5 text-sm leading-relaxed text-amber-950 dark:text-amber-50">
            {uncertaintyLines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <button
        type="button"
        className="text-sm font-medium text-blue-600 underline-offset-2 hover:underline dark:text-blue-400"
        aria-expanded={open}
        onClick={() => setOpen((x) => !x)}
      >
        {open ? "Скрыть подробности" : "Подробности"}
      </button>

      {open ? (
        <motion.div
          className="mt-4 space-y-4 border-t border-slate-200 pt-4 dark:border-slate-700/80"
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          transition={{ duration: 0.2 }}
        >
          <p className="text-xs text-slate-500">
            Диагностический статус:{" "}
            <span className="font-medium text-slate-700 dark:text-slate-300">
              {humanizeFaceVerifyStatus(v.status)}
            </span>
          </p>

          <div className="rounded-lg border border-slate-200/80 bg-slate-50/60 p-3 text-xs dark:border-slate-600/50 dark:bg-slate-950/30">
            <p className="mb-1.5 font-medium text-slate-700 dark:text-slate-200">
              Пороги (справочно)
            </p>
            <ul className="space-y-0.5 tabular-nums text-slate-600 dark:text-slate-400">
              <li>
                Сильная галерея: ≥ {pctExact(v.threshold_verified_strong)}%
              </li>
              <li>Слабая галерея: ≥ {pctExact(v.threshold_verified_weak)}%</li>
              <li>Применён сейчас: {pctExact(v.threshold_applied)}%</li>
            </ul>
          </div>

          <div className="rounded-lg border border-slate-200/80 bg-slate-50/60 p-3 text-xs dark:border-slate-600/50 dark:bg-slate-950/30">
            <p className="mb-1.5 font-medium text-slate-700 dark:text-slate-200">
              Качество кадра
            </p>
            <p className="text-slate-600 dark:text-slate-400">
              {v.quality.passed
                ? "Достаточно для сравнения."
                : "Есть замечания — см. коды ниже."}
            </p>
            {typeof v.quality.det_score === "number" ? (
              <p className="mt-1 tabular-nums text-slate-500">
                Уверенность детектора: {v.quality.det_score.toFixed(3)}
              </p>
            ) : null}
            {typeof v.quality.face_area_ratio === "number" ? (
              <p className="tabular-nums text-slate-500">
                Доля лица: {(v.quality.face_area_ratio * 100).toFixed(2)}%
              </p>
            ) : null}
          </div>

          <div className="rounded-lg border border-slate-200/80 bg-slate-50/60 p-3 text-xs dark:border-slate-600/50 dark:bg-slate-950/30">
            <p className="mb-2 font-medium text-slate-700 dark:text-slate-200">
              Проверка фото
            </p>
            {v.liveness.checked ? (
              <VerifyPadLivenessDetails
                liveness={v.liveness}
                padBarsOpen={padBarsOpen}
                setPadBarsOpen={setPadBarsOpen}
              />
            ) : null}
          </div>

          <motion.div
            variants={fadeContainer}
            initial="hidden"
            animate="show"
            className="rounded-lg border border-slate-200/80 bg-slate-50/60 p-3 dark:border-slate-600/50 dark:bg-slate-950/30"
          >
            <p className="mb-2 text-xs font-medium text-slate-700 dark:text-slate-200">
              Сходство (детальнее)
            </p>
            <Bar
              label="Основной скор"
              value={v.score}
              tone={yes ? "emerald" : "rose"}
            />
            <Bar
              label="Лучшее совпадение с эталоном"
              value={v.max_cosine}
              tone="slate"
            />
          </motion.div>

          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-500 sm:grid-cols-3">
            <div>
              <dt>Эталонов</dt>
              <dd className="text-slate-600 dark:text-slate-400">
                {v.gallery_size}
              </dd>
            </div>
            <div>
              <dt>Источников эталона</dt>
              <dd className="text-slate-600 dark:text-slate-400">
                {v.gallery.distinct_enrollment_sources}
              </dd>
            </div>
            {v.diagnostics?.mode_used ? (
              <div>
                <dt>Режим</dt>
                <dd className="font-mono text-[11px] text-slate-600 dark:text-slate-400">
                  {v.diagnostics.mode_used}
                </dd>
              </div>
            ) : null}
          </dl>

          {v.diagnostics &&
          typeof v.diagnostics.gallery_breakdown === "object" &&
          v.diagnostics.gallery_breakdown !== null ? (
            <div className="rounded-lg border border-slate-200/80 p-2 text-[11px] text-slate-600 dark:border-slate-600/50 dark:text-slate-400">
              <p className="mb-1 font-medium text-slate-700 dark:text-slate-300">
                Разбивка галереи
              </p>
              <dl className="space-y-1">
                {Object.entries(v.diagnostics.gallery_breakdown).map(
                  ([key, val]) => (
                    <div
                      key={key}
                      className="flex justify-between gap-2 border-b border-slate-200/60 pb-1 last:border-0 dark:border-slate-700/50"
                    >
                      <dt className="text-slate-500 dark:text-slate-400">
                        {key.replace(/_/g, " ")}
                      </dt>
                      <dd className="tabular-nums font-medium text-slate-800 dark:text-slate-200">
                        {typeof val === "number" ? val : String(val)}
                      </dd>
                    </div>
                  ),
                )}
              </dl>
            </div>
          ) : null}

          {v.reason_codes.length > 0 ? (
            <div>
              <p className="mb-1 text-xs font-medium text-slate-500">
                Коды решения
              </p>
              <ul className="list-inside list-disc space-y-0.5 text-xs text-slate-600 dark:text-slate-400">
                {v.reason_codes.map((c) => (
                  <li key={c}>{humanizeVerifyReasonCode(c)}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </motion.div>
      ) : null}
    </motion.div>
  );
}
