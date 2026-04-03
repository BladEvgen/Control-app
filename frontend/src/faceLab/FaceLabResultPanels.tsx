import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { FaFolderOpen, FaHashtag, FaListUl, FaTable } from "react-icons/fa";
import {
  isRecord,
  parseRecognizeResponse,
  parseVerifyResponse,
  type PadTestResponse,
  type RecognizeResponse,
  type VerifyResponse,
} from "./faceLabApi";
import { formatServerElapsed } from "./faceLabFormat";
import {
  humanizeApiError,
  humanizeApiTokenString,
  humanizePadStatus,
  humanizePadTag,
  humanizeResponseFieldKey,
  humanizeUnknownFaceStatus,
  humanizeVerifyMode,
} from "./faceLabHumanMessages";

export type {
  PadTestResponse,
  RecognizeResponse,
  RecognizedStaffRow,
  UnknownFaceRow,
  VerifyResponse,
} from "./faceLabApi";

const fadeContainer = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.055, delayChildren: 0.03 },
  },
};

const fadeItem = {
  hidden: { opacity: 0, y: 10 },
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

function bestVerifyDisplayScore(v: VerifyResponse): number {
  if (typeof v.max_cosine === "number") {
    return Math.max(v.score, v.max_cosine);
  }
  return v.score;
}

const springBar: { type: "spring"; stiffness: number; damping: number; mass: number } = {
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
        <div className="flex flex-col items-end gap-0.5">
          <span className="tabular-nums text-xl font-semibold tracking-tight text-slate-900 dark:text-slate-50 sm:text-2xl">
            {pctStr}
            <span className="text-base font-semibold text-slate-500 dark:text-slate-400">%</span>
          </span>
        </div>
      </div>
      <div className="relative h-2.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
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

export function PadResultPanel({ pad }: { pad: PadTestResponse }) {
  const trustOk = pad.trust_confirmed === true;
  const trustBad = pad.trust_confirmed === false;
  return (
    <motion.div
      className="rounded-xl border border-slate-200 bg-white/95 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/60 sm:p-5"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
    >
      <motion.div
        className="mb-3 flex flex-wrap items-center gap-2"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: "spring" as const, stiffness: 380, damping: 28 }}
      >
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">Живость на сервере</h3>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
            trustOk
              ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300"
              : trustBad
                ? "bg-rose-500/15 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300"
                : "bg-slate-200 text-slate-700 dark:bg-slate-600/40 dark:text-slate-300"
          }`}
        >
          {trustOk
            ? "Кадр принят"
            : trustBad
              ? "Подозрение на подмену"
              : "Нужна осторожность"}
        </span>
      </motion.div>
      <motion.p
        className="mb-4 text-sm text-slate-600 dark:text-slate-400"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.08 }}
      >
        {humanizePadStatus(pad.status)}
      </motion.p>
      <motion.div
        className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
        variants={fadeContainer}
        initial="hidden"
        animate="show"
      >
        <Bar
          label="Риск подмены"
          value={pad.risk_score}
          tone={pad.risk_score > 0.45 ? "rose" : pad.risk_score > 0.25 ? "amber" : "emerald"}
        />
        <Bar label="Подлинность лица" value={pad.deepface_score} tone="slate" />
        <Bar label="Съёмка с экрана" value={pad.device_score} tone="slate" />
        <Bar label="Рамка кадра" value={pad.frame_score} tone="slate" />
        <Bar label="Чёткость и размер лица" value={pad.quality_penalty} tone="amber" />
      </motion.div>
      {pad.tags.length > 0 ? (
        <motion.div
          className="mb-3"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
        >
          <p className="mb-1.5 text-xs font-medium text-slate-500">Замечания</p>
          <motion.div
            className="flex flex-wrap gap-1.5"
            variants={fadeContainer}
            initial="hidden"
            animate="show"
          >
            {pad.tags.map((t) => (
              <motion.span
                key={t}
                variants={fadeItem}
                className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-700 dark:border-slate-600/80 dark:bg-slate-950/80 dark:text-slate-300"
                title={t}
              >
                {humanizePadTag(t)}
              </motion.span>
            ))}
          </motion.div>
        </motion.div>
      ) : null}
      <motion.dl
        className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-500 sm:grid-cols-3"
        variants={fadeContainer}
        initial="hidden"
        animate="show"
      >
        <motion.div variants={fadeItem}>
          <dt>Версия</dt>
          <dd className="font-mono text-[11px] text-slate-600 dark:text-slate-400">{pad.model_version}</dd>
        </motion.div>
        <motion.div variants={fadeItem}>
          <dt>Время на сервере</dt>
          <dd className="text-slate-600 dark:text-slate-400">
            {formatServerElapsed(pad.elapsed_ms)}
            <span className="ml-1.5 font-mono text-[10px] text-slate-500 dark:text-slate-600">
              ({pad.elapsed_ms} мс)
            </span>
          </dd>
        </motion.div>
      </motion.dl>
    </motion.div>
  );
}

export function VerifyResultPanel({ v }: { v: VerifyResponse }) {
  const displayBest = bestVerifyDisplayScore(v);
  return (
    <motion.div
      className="rounded-xl border border-slate-200 bg-white/95 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/60 sm:p-5"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
    >
      <motion.div
        className="mb-3 flex flex-wrap items-center gap-2"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: "spring" as const, stiffness: 380, damping: 28 }}
      >
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">Сравнение с эталоном</h3>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
            v.verified
              ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300"
              : "bg-rose-50 text-rose-800 dark:bg-rose-500/20 dark:text-rose-300"
          }`}
        >
          {v.verified ? "Похоже на того же человека" : "Совпадение ниже порога"}
        </span>
      </motion.div>
      <motion.p
        className="mb-4 text-sm text-slate-600 dark:text-slate-400"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.06 }}
      >
        {v.verified
          ? "Сходство с эталонами выше порога."
          : "Ниже порога. Попробуйте другой ракурс или свет."}
      </motion.p>
      <motion.div
        className="mb-4 flex flex-col items-center justify-center rounded-2xl border border-slate-200/90 bg-gradient-to-b from-slate-50 to-white py-5 dark:border-slate-600/60 dark:from-slate-900/80 dark:to-slate-950/60 sm:py-6"
        initial={{ opacity: 0, scale: 0.92 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: "spring", stiffness: 360, damping: 24, mass: 0.85 }}
      >
        <span className="text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Итоговое сходство
        </span>
        <span
          className={`mt-1 tabular-nums text-4xl font-bold tracking-tight sm:text-5xl ${
            v.verified ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
          }`}
        >
          {pctExact(displayBest)}
          <span className="text-2xl font-bold text-slate-400 dark:text-slate-500 sm:text-3xl">%</span>
        </span>
        {typeof v.threshold_used === "number" ? (
          <span className="mt-2 text-xs text-slate-500 dark:text-slate-400">
            Порог:{" "}
            <span className="tabular-nums font-semibold text-slate-600 dark:text-slate-300">
              {pctExact(v.threshold_used)}%
            </span>
          </span>
        ) : null}
      </motion.div>
      <motion.div
        variants={fadeContainer}
        initial="hidden"
        animate="show"
        className="space-y-3"
      >
        <Bar label="Сходство (шкала)" value={v.score} tone={v.verified ? "emerald" : "rose"} />
        {typeof v.max_cosine === "number" ? (
          <Bar
            label="Лучшее совпадение с эталоном"
            value={v.max_cosine}
            tone={v.verified ? "emerald" : "rose"}
          />
        ) : null}
      </motion.div>
      <motion.dl
        className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-500 sm:grid-cols-3"
        variants={fadeContainer}
        initial="hidden"
        animate="show"
      >
        {typeof v.gallery_templates === "number" ? (
          <motion.div variants={fadeItem}>
            <dt>Сколько эталонов сравнивали</dt>
            <dd className="text-slate-600 dark:text-slate-400">{v.gallery_templates}</dd>
          </motion.div>
        ) : null}
        {typeof v.threshold_used === "number" ? (
          <motion.div variants={fadeItem}>
            <dt>Порог «достаточно похоже»</dt>
            <dd className="tabular-nums text-slate-600 dark:text-slate-400">
              <span className="font-semibold">{pctExact(v.threshold_used)}%</span>
              <span className="ml-1.5 text-[11px] text-slate-500 dark:text-slate-500">
                (доля {v.threshold_used.toFixed(4)})
              </span>
            </dd>
          </motion.div>
        ) : null}
        {typeof v.trained_model_present === "boolean" ? (
          <motion.div variants={fadeItem}>
            <dt>Доп. обучение под сотрудника</dt>
            <dd className="text-slate-600 dark:text-slate-400">{v.trained_model_present ? "есть" : "нет"}</dd>
          </motion.div>
        ) : null}
        {typeof v.verification_mode === "string" ? (
          <motion.div variants={fadeItem} className="col-span-2 sm:col-span-3">
            <dt>Режим сравнения</dt>
            <dd className="text-slate-600 dark:text-slate-400">{humanizeVerifyMode(v.verification_mode)}</dd>
          </motion.div>
        ) : null}
      </motion.dl>
      {v.relaxed_match === true ? (
        <motion.p
          className="mt-3 text-xs text-amber-800 dark:text-amber-300/90"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
        >
          Совпадение подтверждено с допуском по ракурсу: оценка близка к порогу, но другие эталоны
          заметно слабее.
        </motion.p>
      ) : null}
    </motion.div>
  );
}

export function RecognizeResultPanel({ r }: { r: RecognizeResponse }) {
  return (
    <motion.div
      className="rounded-xl border border-slate-200 bg-white/95 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/60 sm:p-5"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
    >
      <motion.div
        className="mb-3 flex flex-wrap items-center gap-2"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: "spring" as const, stiffness: 380, damping: 28 }}
      >
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">Галерея</h3>
        <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-300">
          Найдено: {r.recognized_staff.length} · без совпадения: {r.unknown_faces.length}
        </span>
      </motion.div>
      {r.recognized_staff.length > 0 ? (
        <motion.p
          className="mb-4 text-sm text-slate-600 dark:text-slate-400"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          Лучшее сходство в ответе:{" "}
          <span className="tabular-nums font-semibold text-emerald-700 dark:text-emerald-400">
            {pctExact(Math.max(...r.recognized_staff.map((row) => row.similarity)))}%
          </span>
        </motion.p>
      ) : null}
      {r.recognized_staff.length === 0 ? (
        <motion.p
          className="text-sm leading-relaxed text-slate-600 dark:text-slate-400"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          По базе совпадений нет — лицо на кадре могло не дойти до порога схожести. Попробуйте крупнее и
          ровнее по свету; если в организации ещё не все маски заведены, поиск может быть пустым.
        </motion.p>
      ) : (
        <motion.ul
          className="grid gap-3 sm:grid-cols-2"
          variants={fadeContainer}
          initial="hidden"
          animate="show"
        >
          {r.recognized_staff.map((row, i) => (
            <motion.li
              key={`${row.pin}-${i}`}
              variants={fadeItem}
              className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700/80 dark:bg-slate-950/50"
              whileHover={{ scale: 1.01 }}
              transition={{ type: "spring", stiffness: 400, damping: 28 }}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1 text-sm font-medium text-slate-900 dark:text-slate-100">
                  {[row.surname, row.name].filter(Boolean).join(" ") || "Имя не указано"}
                </div>
                <motion.div
                  className="flex shrink-0 flex-col items-end"
                  initial={{ opacity: 0, scale: 0.85 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ type: "spring", stiffness: 400, damping: 22 }}
                >
                  <span className="text-[10px] font-medium uppercase tracking-wide text-emerald-700/90 dark:text-emerald-400/90">
                    Схожесть
                  </span>
                  <span className="tabular-nums text-2xl font-bold leading-none text-emerald-600 dark:text-emerald-400">
                    {pctExact(row.similarity)}
                    <span className="text-lg font-bold text-emerald-700/70 dark:text-emerald-500/80">%</span>
                  </span>
                </motion.div>
              </div>
              {row.department ? (
                <p className="mt-1 text-xs text-slate-600 dark:text-slate-500">{row.department}</p>
              ) : null}
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-600">Служебный PIN: {row.pin}</p>
            </motion.li>
          ))}
        </motion.ul>
      )}
      {r.unknown_faces.length > 0 ? (
        <motion.div
          className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-900/40 dark:bg-amber-950/20"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.12 }}
        >
          <p className="text-xs font-medium text-amber-900 dark:text-amber-200/90">
            Лица без совпадения с галереей ({r.unknown_faces.length})
          </p>
          <motion.ul
            className="mt-2 space-y-1 text-xs text-amber-900/85 dark:text-amber-100/85"
            variants={fadeContainer}
            initial="hidden"
            animate="show"
          >
            {r.unknown_faces.map((uf, i) => (
              <motion.li key={i} variants={fadeItem}>
                Лицо {i + 1}: {humanizeUnknownFaceStatus(uf.status)}
              </motion.li>
            ))}
          </motion.ul>
        </motion.div>
      ) : null}
    </motion.div>
  );
}

function formatUnknownValue(v: unknown, depth: number, fieldKey?: string): ReactNode {
  if (depth > 4) return "…";
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "да" : "нет";
  if (typeof v === "number") {
    if (fieldKey === "elapsed_ms") {
      return (
        <>
          {formatServerElapsed(v)}
          <span className="ml-1.5 font-mono text-[10px] text-slate-500 dark:text-slate-600">
            ({Math.round(v)} мс)
          </span>
        </>
      );
    }
    if (Number.isInteger(v)) return String(v);
    const t = v.toFixed(4).replace(/\.?0+$/, "");
    return t || "0";
  }
  if (typeof v === "string") return humanizeApiTokenString(v);
  if (Array.isArray(v)) {
    if (v.length === 0) return "нет";
    if (v.every((x) => typeof x === "number")) {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400">
          <FaHashtag className="h-3 w-3 opacity-70" aria-hidden />
          область на кадре (координаты)
        </span>
      );
    }
    return (
      <div className="flex gap-2 rounded-lg border border-slate-200/90 bg-slate-50/80 p-2 dark:border-slate-600/50 dark:bg-slate-900/35">
        <FaListUl className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden />
        <ul className="list-none space-y-1.5 text-xs">
          {v.slice(0, 24).map((item, i) => (
            <li
              key={i}
              className="border-b border-slate-200/60 pb-1.5 last:border-0 last:pb-0 dark:border-slate-600/40"
            >
              {formatUnknownValue(item, depth + 1)}
            </li>
          ))}
          {v.length > 24 ? (
            <li className="text-slate-500">… ещё {v.length - 24}</li>
          ) : null}
        </ul>
      </div>
    );
  }
  if (isRecord(v)) {
    const entries = Object.entries(v);
    if (entries.length === 0) return "—";
    return (
      <div className="mt-1 rounded-lg border border-slate-200/90 bg-gradient-to-b from-slate-50/90 to-white/50 p-2.5 text-xs dark:border-slate-600/55 dark:from-slate-900/45 dark:to-slate-950/30">
        <div className="mb-2 flex items-center gap-1.5 font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
          <FaFolderOpen className="h-3.5 w-3.5" aria-hidden />
          Вложенные поля
        </div>
        <dl className="space-y-2">
          {entries.map(([k, val]) => (
            <div
              key={k}
              className="rounded-md border border-slate-100/80 bg-white/60 px-2 py-1.5 dark:border-slate-700/50 dark:bg-slate-900/25"
            >
              <dt className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
                {humanizeResponseFieldKey(k)}
              </dt>
              <dd className="mt-0.5 text-slate-800 dark:text-slate-200">
                {formatUnknownValue(val, depth + 1, k)}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    );
  }
  return String(v);
}

export function UnexpectedPayloadPanel({ data }: { data: unknown }) {
  if (data === null || data === undefined) {
    return (
      <p className="text-sm text-slate-600 dark:text-slate-400">Пустой ответ сервера. Попробуйте ещё раз.</p>
    );
  }
  if (!isRecord(data)) {
    return (
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Не удалось разобрать ответ. Если проблема повторяется, обратитесь к администратору.
      </p>
    );
  }
  const entries = Object.entries(data).filter(([, val]) => val !== undefined);
  if (entries.length === 0) {
    return (
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Ответ без полезных полей. Попробуйте другое фото или повторите позже.
      </p>
    );
  }
  return (
    <motion.div
      className="rounded-xl border border-slate-200 bg-white/95 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/60 sm:p-5"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
    >
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-200/90 text-slate-600 dark:bg-slate-700 dark:text-slate-300">
          <FaTable className="h-4 w-4" aria-hidden />
        </span>
        <div>
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">Нестандартный ответ</h3>
          <p className="text-xs text-slate-500">Поля разобраны ниже.</p>
        </div>
      </div>
      <motion.dl
        className="grid gap-3 text-sm sm:grid-cols-2"
        variants={fadeContainer}
        initial="hidden"
        animate="show"
      >
        {entries.map(([k, val]) => (
          <motion.div key={k} variants={fadeItem}>
            <dt className="text-xs font-medium text-slate-500">{humanizeResponseFieldKey(k)}</dt>
            <dd className="mt-0.5 text-slate-800 dark:text-slate-200">{formatUnknownValue(val, 0, k)}</dd>
          </motion.div>
        ))}
      </motion.dl>
    </motion.div>
  );
}

export function ApiErrorPanel({ data }: { data: unknown }) {
  if (!isRecord(data) || typeof data.error !== "string") return null;
  const { title, detail } = humanizeApiError(data.error);
  const serverDetail =
    typeof data.detail === "string" && data.detail.trim() ? data.detail.trim() : null;
  return (
    <motion.div
      className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-950 dark:border-amber-800/50 dark:bg-amber-950/25 dark:text-amber-100"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32 }}
    >
      <p className="font-medium">{title}</p>
      {detail ? (
        <p className="mt-2 text-sm text-amber-800/90 dark:text-amber-200/90">{detail}</p>
      ) : null}
      {serverDetail && serverDetail !== detail ? (
        <p className="mt-2 text-sm text-amber-800/85 dark:text-amber-200/80">{serverDetail}</p>
      ) : null}
    </motion.div>
  );
}

export function RecognizeOrRaw({ data }: { data: unknown }) {
  const rec = parseRecognizeResponse(data);
  if (rec) {
    return <RecognizeResultPanel r={rec} />;
  }
  if (isRecord(data) && typeof data.error === "string") {
    return <ApiErrorPanel data={data} />;
  }
  return <UnexpectedPayloadPanel data={data} />;
}

export function VerifyOrRaw({ data }: { data: unknown }) {
  const ver = parseVerifyResponse(data);
  if (ver) {
    return <VerifyResultPanel v={ver} />;
  }
  if (isRecord(data) && typeof data.error === "string") {
    return <ApiErrorPanel data={data} />;
  }
  return <UnexpectedPayloadPanel data={data} />;
}
