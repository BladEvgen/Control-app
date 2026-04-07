import { useState } from "react";
import { motion } from "framer-motion";
import type { FaceVerifyApiResponse } from "./faceLabApi";
import { formatServerElapsed } from "./faceLabFormat";
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
  if (g === "strong") return "Надёжная галерея эталонов.";
  return "Слабая галерея эталонов — применён строгий порог.";
}

function livenessSummary(v: FaceVerifyApiResponse): string {
  if (v.status === "PAD_ERROR")
    return "Проверка живости не выполнена (техническая ошибка).";
  if (v.status === "LIVENESS_FAIL") return "Живость не подтверждена.";
  if (
    v.liveness.checked &&
    v.liveness.trust_confirmed === true &&
    v.liveness.status === "clean"
  ) {
    return "Живость подтверждена.";
  }
  if (v.liveness.checked) return "Живость не подтверждена.";
  return "Результат живости отсутствует.";
}

export function VerifyContractPanel({ v }: { v: FaceVerifyApiResponse }) {
  const [open, setOpen] = useState(false);
  const yes = v.matched && v.final_decision === "YES";
  const displayScore = Math.max(v.score, v.max_cosine);

  return (
    <motion.div
      className="rounded-xl border border-slate-200 bg-white/95 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/60 sm:p-5"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
          Сравнение с эталоном
        </h3>
        <span
          className={`rounded-full px-3 py-0.5 text-sm font-semibold ${
            yes
              ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300"
              : "bg-rose-50 text-rose-800 dark:bg-rose-500/20 dark:text-rose-300"
          }`}
        >
          {v.final_decision}
        </span>
      </div>

      <p className="mb-3 text-sm text-slate-700 dark:text-slate-300">
        {(v.summary || v.decision_summary || "").trim()}
      </p>

      <div className="mb-3 rounded-lg border border-slate-200/90 bg-slate-50/90 px-3 py-2.5 text-sm dark:border-slate-600/60 dark:bg-slate-950/40">
        <p className="tabular-nums font-medium text-slate-800 dark:text-slate-200">
          Сходство:{" "}
          <span
            className={
              yes
                ? "text-emerald-700 dark:text-emerald-400"
                : "text-slate-900 dark:text-slate-100"
            }
          >
            {pctExact(displayScore)}%
          </span>
          <span className="mx-1.5 text-slate-400">·</span>
          порог для этого кадра: {pctExact(v.threshold_applied)}%
        </p>
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
          {livenessSummary(v)}
        </p>
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
          {galleryStrengthLine(v.gallery_strength)}
        </p>
      </div>

      <button
        type="button"
        className="text-sm font-medium text-blue-600 underline-offset-2 hover:underline dark:text-blue-400"
        aria-expanded={open}
        onClick={() => setOpen((x) => !x)}
      >
        {open ? "Скрыть технические детали" : "Технические детали"}
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
              Живость (PAD), метрики
            </p>
            {v.liveness.checked && typeof v.liveness.status === "string" ? (
              <p className="mb-2 text-slate-600 dark:text-slate-400">
                {humanizePadStatus(v.liveness.status)}
              </p>
            ) : null}
            {v.liveness.checked &&
            typeof v.liveness.risk_score === "number" &&
            typeof v.liveness.deepface_score === "number" ? (
              <motion.div
                className="space-y-2"
                variants={fadeContainer}
                initial="hidden"
                animate="show"
              >
                <Bar
                  label="Риск подмены"
                  value={v.liveness.risk_score}
                  tone={
                    v.liveness.risk_score > 0.45
                      ? "rose"
                      : v.liveness.risk_score > 0.25
                        ? "amber"
                        : "emerald"
                  }
                />
                <Bar
                  label="Подлинность лица (FasNet)"
                  value={v.liveness.deepface_score}
                  tone="slate"
                />
                {typeof v.liveness.device_score === "number" ? (
                  <Bar
                    label="Съёмка с экрана"
                    value={v.liveness.device_score}
                    tone="slate"
                  />
                ) : null}
                {typeof v.liveness.frame_score === "number" ? (
                  <Bar
                    label="Рамка кадра"
                    value={v.liveness.frame_score}
                    tone="slate"
                  />
                ) : null}
                {typeof v.liveness.quality_penalty === "number" ? (
                  <Bar
                    label="Штраф за качество"
                    value={v.liveness.quality_penalty}
                    tone="amber"
                  />
                ) : null}
              </motion.div>
            ) : null}
            {v.liveness.checked &&
            v.liveness.tags &&
            v.liveness.tags.length > 0 ? (
              <div className="mt-2">
                <p className="mb-1 text-[11px] font-medium text-slate-500">
                  Теги PAD
                </p>
                <div className="flex flex-wrap gap-1">
                  {v.liveness.tags.map((tag) => (
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
            {v.liveness.checked &&
            typeof v.liveness.elapsed_ms === "number" &&
            typeof v.liveness.model_version === "string" ? (
              <p className="mt-2 tabular-nums text-[11px] text-slate-500">
                {v.liveness.model_version} ·{" "}
                {formatServerElapsed(v.liveness.elapsed_ms)} (
                {v.liveness.elapsed_ms.toFixed(0)} мс)
              </p>
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
              <pre className="overflow-x-auto font-mono text-[10px]">
                {JSON.stringify(v.diagnostics.gallery_breakdown, null, 0)}
              </pre>
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
