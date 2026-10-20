import type { ReactNode } from "react";
import { motion } from "framer-motion";
import {
  FaCheck,
  FaFolderOpen,
  FaHashtag,
  FaListUl,
  FaTable,
} from "react-icons/fa";
import {
  isRecord,
  parseRecognizeResponse,
  parseVerifyPayload,
  type PadTestResponse,
  type RecognizeResponse,
} from "./faceLabApi";
import { VerifyContractPanel } from "./faceLabVerifyComparePanels";
import { formatServerElapsed } from "./faceLabFormat";
import {
  humanizeApiError,
  humanizeApiTokenString,
  humanizeGallerySearchError,
  humanizeResponseFieldKey,
} from "./faceLabHumanMessages";
import { PadDecisionCard } from "./faceLabPadDiagnostics";
import { AnimatedPercent } from "./faceLabDesign";
import {
  clamp01,
  faceLabBadgeClass,
  faceLabFadeContainer,
  faceLabFadeItem,
  pctExact,
} from "./faceLabDesignTokens";

export type {
  PadTestResponse,
  RecognizeResponse,
  RecognizedStaffRow,
  UnknownFaceRow,
} from "./faceLabApi";
export { VerifyContractPanel } from "./faceLabVerifyComparePanels";

export function PadResultPanel({ pad }: { pad: PadTestResponse }) {
  return <PadDecisionCard decision={pad.decision} />;
}

export function RecognizeResultPanel({ r }: { r: RecognizeResponse }) {
  const matches = [...r.recognized_staff].sort(
    (a, b) => b.similarity - a.similarity,
  );
  const bestUnknown = r.unknown_faces.reduce<number | null>(
    (best, uf) =>
      typeof uf.best_similarity === "number" &&
      (best === null || uf.best_similarity > best)
        ? uf.best_similarity
        : best,
    null,
  );

  return (
    <motion.div
      className="rounded-xl border border-slate-200 bg-white/95 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/60 sm:p-5"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          {matches.length === 0
            ? "Никого не нашли"
            : matches.length === 1
              ? "Найден в базе"
              : `Найдено в базе: ${matches.length}`}
        </h3>
        {/* Recognition runs only after the photo check said YES. */}
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${faceLabBadgeClass("success")}`}
        >
          <FaCheck aria-hidden className="h-3 w-3" />
          Фото живое
        </span>
      </div>

      {matches.length === 0 ? (
        <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">
          В базе нет достаточно похожего человека.
          {bestUnknown !== null
            ? ` Самое близкое сходство ${pctExact(bestUnknown)}%, этого мало для совпадения.`
            : null}{" "}
          Снимите лицо ближе и прямо или проверьте, есть ли у сотрудника фото в
          профиле.
        </p>
      ) : (
        <motion.ul
          className="grid gap-3"
          variants={faceLabFadeContainer}
          initial="hidden"
          animate="show"
        >
          {matches.map((row, i) => {
            const name =
              [row.surname, row.name].filter(Boolean).join(" ") ||
              "Имя не указано";
            const nextBest =
              typeof row.neighbor_gap === "number" && row.neighbor_gap < 1
                ? row.similarity - row.neighbor_gap
                : null;
            return (
              <motion.li
                key={`${row.pin}-${i}`}
                variants={faceLabFadeItem}
                className="flex flex-wrap items-center gap-3 rounded-2xl border border-emerald-200/80 bg-emerald-50/80 p-3 dark:border-emerald-800/40 dark:bg-emerald-500/10"
              >
                {row.avatar_url ? (
                  <img
                    src={row.avatar_url}
                    alt=""
                    className="h-12 w-12 shrink-0 rounded-full border border-slate-200 object-cover dark:border-slate-700"
                  />
                ) : (
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-slate-100 text-sm font-semibold uppercase text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
                    {name.slice(0, 1)}
                  </span>
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {name}
                    <span className="ml-2 font-mono text-[11px] font-normal text-slate-400">
                      {row.pin}
                    </span>
                  </p>
                  {row.department ? (
                    <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">
                      {row.department}
                    </p>
                  ) : null}
                  {nextBest !== null ? (
                    <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
                      Следующий похожий сотрудник: {pctExact(nextBest)}%
                    </p>
                  ) : null}
                </div>
                <div className="text-right">
                  <span className="block text-[10px] font-medium uppercase text-slate-500 dark:text-slate-400">
                    Сходство
                  </span>
                  <span className="block tabular-nums text-xl font-bold leading-none text-emerald-700 dark:text-emerald-300">
                    <AnimatedPercent
                      value={clamp01(row.similarity) * 100}
                      decimals={2}
                    />
                    <span className="text-base opacity-70">%</span>
                  </span>
                </div>
              </motion.li>
            );
          })}
        </motion.ul>
      )}

      {matches.length > 0 && r.unknown_faces.length > 0 ? (
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
          Ещё лиц на фото без совпадения в базе: {r.unknown_faces.length}.
        </p>
      ) : null}
    </motion.div>
  );
}

function formatUnknownValue(
  v: unknown,
  depth: number,
  fieldKey?: string,
): ReactNode {
  if (depth > 4) return "…";
  if (v === null || v === undefined) return "нет данных";
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
        <FaListUl
          className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400"
          aria-hidden
        />
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
    if (entries.length === 0) return "пусто";
    return (
      <div className="mt-1 rounded-lg border border-slate-200/90 bg-gradient-to-b from-slate-50/90 to-white/50 p-2.5 text-xs dark:border-slate-600/55 dark:from-slate-900/45 dark:to-slate-950/30">
        <div className="mb-2 flex items-center gap-1.5 font-semibold uppercase text-slate-400 dark:text-slate-500">
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
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Пустой ответ сервера. Попробуйте ещё раз.
      </p>
    );
  }
  if (!isRecord(data)) {
    return (
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Не удалось разобрать ответ. Если проблема повторяется, обратитесь к
        администратору.
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
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
            Нестандартный ответ
          </h3>
          <p className="text-xs text-slate-500">Поля разобраны ниже.</p>
        </div>
      </div>
      <motion.dl
        className="grid gap-3 text-sm sm:grid-cols-2"
        variants={faceLabFadeContainer}
        initial="hidden"
        animate="show"
      >
        {entries.map(([k, val]) => (
          <motion.div key={k} variants={faceLabFadeItem}>
            <dt className="text-xs font-medium text-slate-500">
              {humanizeResponseFieldKey(k)}
            </dt>
            <dd className="mt-0.5 text-slate-800 dark:text-slate-200">
              {formatUnknownValue(val, 0, k)}
            </dd>
          </motion.div>
        ))}
      </motion.dl>
    </motion.div>
  );
}

export function ApiErrorPanel({
  data,
  humanize = humanizeApiError,
}: {
  data: unknown;
  humanize?: (raw: string) => { title: string; detail?: string | null };
}) {
  if (!isRecord(data) || typeof data.error !== "string") return null;
  const { title, detail } = humanize(data.error);
  const serverDetail =
    typeof data.detail === "string" && data.detail.trim()
      ? data.detail.trim()
      : null;
  return (
    <motion.div
      className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-950 dark:border-amber-800/50 dark:bg-amber-950/25 dark:text-amber-100"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32 }}
    >
      <p className="font-medium">{title}</p>
      {detail ? (
        <p className="mt-2 text-sm text-amber-800/90 dark:text-amber-200/90">
          {detail}
        </p>
      ) : null}
      {serverDetail && serverDetail !== detail ? (
        <p className="mt-2 text-sm text-amber-800/85 dark:text-amber-200/80">
          {serverDetail}
        </p>
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
    return <ApiErrorPanel data={data} humanize={humanizeGallerySearchError} />;
  }
  return <UnexpectedPayloadPanel data={data} />;
}

export function VerifyOrRaw({ data }: { data: unknown }) {
  const parsed = parseVerifyPayload(data);
  if (parsed) {
    return <VerifyContractPanel v={parsed} />;
  }
  if (isRecord(data) && typeof data.error === "string") {
    return <ApiErrorPanel data={data} />;
  }
  return <UnexpectedPayloadPanel data={data} />;
}
