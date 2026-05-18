import React, { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { AreaSequencePoint } from "../../schemas/IData";

type Props = {
  areaSequence: AreaSequencePoint[] | null | undefined;
  embedded?: boolean;
};

const easeSmooth = [0.22, 1, 0.36, 1] as const;

function parseTime(t: string): number {
  const s = (t || "").trim();
  if (!s) return 0;
  const parsed = Date.parse(s);
  if (!Number.isNaN(parsed)) return parsed;
  const m = /^(\d{1,2}):(\d{2})/.exec(s);
  if (m) return Number(m[1]) * 60 + Number(m[2]);
  return 0;
}

type RouteKind = "entry" | "exit" | "transfer" | "exit_candidate" | "passage";

function classifyPoint(p: AreaSequencePoint, index: number): RouteKind {
  if (p.is_exit === "1") return "exit";
  if (p.exit_resolution === "bridge_transfer") return "transfer";
  if (p.exit_candidate === "1") return "exit_candidate";
  const raw = (p.area || "").toLowerCase();
  if (raw.includes("вход")) return "entry";
  if (raw.includes("выход")) return "exit";
  if (index === 0) return "entry";
  return "passage";
}

function kindLabel(kind: RouteKind): string {
  switch (kind) {
    case "entry":
      return "Вход";
    case "exit":
      return "Выход";
    case "transfer":
      return "Переход";
    case "exit_candidate":
      return "Турникет";
    default:
      return "В здании";
  }
}

function kindDotClass(kind: RouteKind): string {
  switch (kind) {
    case "entry":
      return "bg-emerald-500 shadow-[0_0_0_3px] shadow-emerald-500/15 dark:bg-emerald-400";
    case "exit":
      return "bg-rose-500 shadow-[0_0_0_3px] shadow-rose-500/15 dark:bg-rose-400";
    case "transfer":
      return "bg-amber-500 shadow-[0_0_0_3px] shadow-amber-500/15 dark:bg-amber-400";
    case "exit_candidate":
      return "bg-violet-500 shadow-[0_0_0_3px] shadow-violet-500/15 dark:bg-violet-400";
    default:
      return "bg-gray-400 shadow-[0_0_0_3px] shadow-gray-400/10 dark:bg-gray-500";
  }
}

type Segment = {
  id: string;
  startT: string;
  endT: string;
  area: string;
  kind: RouteKind;
  count: number;
};

function buildSegments(sorted: AreaSequencePoint[]): Segment[] {
  const out: Segment[] = [];

  for (let i = 0; i < sorted.length; i++) {
    const p = sorted[i];
    const kind = classifyPoint(p, i);
    const atomic =
      kind === "exit" ||
      kind === "transfer" ||
      kind === "exit_candidate" ||
      p.is_exit === "1";

    if (atomic) {
      out.push({
        id: `${p.t}-${i}-${p.area}`,
        startT: p.t,
        endT: p.t,
        area: p.area,
        kind,
        count: 1,
      });
      continue;
    }

    const prev = out[out.length - 1];
    const mergeablePrev =
      prev &&
      (prev.kind === "entry" || prev.kind === "passage") &&
      prev.area === p.area;

    if (mergeablePrev) {
      prev.endT = p.t;
      prev.count += 1;
    } else {
      out.push({
        id: `${p.t}-${i}-${p.area}`,
        startT: p.t,
        endT: p.t,
        area: p.area,
        kind,
        count: 1,
      });
    }
  }

  return out;
}

function formatTimeRange(startT: string, endT: string, count: number): string {
  if (startT === endT) {
    return count > 1 ? `${startT} (${count}×)` : startT;
  }
  return count > 1 ? `${startT}–${endT} (${count}×)` : `${startT}–${endT}`;
}

function middleAnchorIndex(len: number): number {
  if (len < 3) return 0;
  const raw = Math.round((len - 1) / 2);
  return Math.max(1, Math.min(len - 2, raw));
}

function StopColumn({
  seg,
  muted,
  dense,
}: {
  seg: Segment;
  muted?: boolean;
  dense?: boolean;
}) {
  const label = kindLabel(seg.kind);
  const timeStr = formatTimeRange(seg.startT, seg.endT, seg.count);

  return (
    <div
      className={
        "flex min-w-0 flex-col items-center text-center " +
        (dense ? "max-w-[9.5rem]" : "max-w-[11rem]") +
        " " +
        (muted ? "opacity-[0.92]" : "")
      }
    >
      <span
        className={
          (dense ? "size-1.5 " : "size-2 ") +
          `shrink-0 rounded-full ${kindDotClass(seg.kind)}`
        }
        title={label}
      />
      <span
        className={
          (dense ? "mt-1 " : "mt-1.5 ") +
          "font-mono text-[10px] tabular-nums text-gray-500 dark:text-gray-400"
        }
      >
        {timeStr}
      </span>
      <span className="text-[9px] font-medium uppercase tracking-[0.12em] text-gray-400 dark:text-gray-500">
        {label}
      </span>
      <span
        className={
          (dense ? "mt-px " : "mt-0.5 ") +
          "line-clamp-2 w-full text-[10px] font-normal leading-snug text-gray-800 dark:text-gray-200 sm:text-[11px]"
        }
        title={seg.area}
      >
        {seg.area}
      </span>
    </div>
  );
}

function TimelineRiver({ segments }: { segments: Segment[] }) {
  return (
    <div className="relative mx-auto w-full max-w-xl px-1 pb-1 pt-0">
      <div
        className="pointer-events-none absolute bottom-3 left-1/2 top-2 w-px -translate-x-1/2 bg-gradient-to-b from-emerald-500/25 via-gray-300/90 to-rose-500/25 dark:via-gray-600/90"
        aria-hidden
      />
      <ol className="relative m-0 list-none space-y-0 p-0">
        {segments.map((seg, idx) => {
          const onLeft = idx % 2 === 0;
          const label = kindLabel(seg.kind);
          const timeStr = formatTimeRange(seg.startT, seg.endT, seg.count);

          return (
            <li
              key={seg.id}
              className="relative flex min-h-[3.5rem] w-full items-start"
            >
              <div className="absolute left-1/2 top-2 z-20 -translate-x-1/2">
                <span
                  className={`block size-2 rounded-full ring-[3px] ring-white dark:ring-gray-950 ${kindDotClass(seg.kind)}`}
                  title={label}
                />
              </div>

              {onLeft ? (
                <div className="flex w-[50%] shrink-0 justify-end pr-5 pt-0.5">
                  <motion.div
                    initial={{ opacity: 0, x: -14 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{
                      duration: 0.28,
                      delay: idx * 0.04,
                      ease: easeSmooth,
                    }}
                    className="max-w-[13.5rem] text-right"
                  >
                    <div className="inline-block rounded-lg border border-gray-200/70 bg-white/90 px-2.5 py-1.5 text-left align-top shadow-sm dark:border-gray-700/90 dark:bg-gray-900/85">
                      <div className="font-mono text-[10px] tabular-nums text-gray-500 dark:text-gray-400">
                        {timeStr}
                      </div>
                      <div className="text-[9px] font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">
                        {label}
                      </div>
                      <div className="mt-0.5 text-[11px] font-medium leading-snug text-gray-900 dark:text-gray-100">
                        {seg.area}
                      </div>
                    </div>
                  </motion.div>
                </div>
              ) : (
                <div className="ml-auto flex w-[50%] shrink-0 justify-start pl-5 pt-0.5">
                  <motion.div
                    initial={{ opacity: 0, x: 14 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{
                      duration: 0.28,
                      delay: idx * 0.04,
                      ease: easeSmooth,
                    }}
                    className="max-w-[13.5rem] text-left"
                  >
                    <div className="inline-block rounded-lg border border-gray-200/70 bg-white/90 px-2.5 py-1.5 text-left shadow-sm dark:border-gray-700/90 dark:bg-gray-900/85">
                      <div className="font-mono text-[10px] tabular-nums text-gray-500 dark:text-gray-400">
                        {timeStr}
                      </div>
                      <div className="text-[9px] font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">
                        {label}
                      </div>
                      <div className="mt-0.5 text-[11px] font-medium leading-snug text-gray-900 dark:text-gray-100">
                        {seg.area}
                      </div>
                    </div>
                  </motion.div>
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

const AttendanceAreaSequenceMap: React.FC<Props> = ({
  areaSequence,
  embedded = false,
}) => {
  const [expanded, setExpanded] = useState(false);

  const segments = useMemo(() => {
    if (!areaSequence?.length) return [];
    const sorted = [...areaSequence].sort(
      (a, b) => parseTime(a.t) - parseTime(b.t),
    );
    return buildSegments(sorted);
  }, [areaSequence]);

  if (segments.length === 0) return null;

  const first = segments[0];
  const last = segments[segments.length - 1];
  const hasMiddle = segments.length > 2;
  const midIdx = hasMiddle ? middleAnchorIndex(segments.length) : 0;
  const mid = hasMiddle ? segments[midIdx] : first;
  const hiddenBetween = segments.length > 3 ? segments.length - 3 : 0;
  const showExpand = hasMiddle && hiddenBetween > 0;

  const shell = embedded
    ? "w-full overflow-x-hidden"
    : "mt-1.5 w-full max-w-full overflow-x-hidden rounded-2xl border border-gray-200/55 bg-white/40 px-3 py-3 shadow-sm dark:border-gray-800/70 dark:bg-gray-950/35 sm:px-4";

  const collapseSummary = (
    <>
      {segments.length === 1 ? (
        <div className="mx-auto flex max-w-xs justify-center py-1">
          <StopColumn seg={first} />
        </div>
      ) : !hasMiddle ? (
        <div className="mx-auto flex max-w-md items-start justify-center gap-2 px-2 sm:gap-6">
          <StopColumn seg={first} />
          <div
            className="mt-2.5 flex shrink-0 items-center self-start pt-1"
            aria-hidden
          >
            <div className="h-px w-8 bg-gray-300/90 dark:bg-gray-700 sm:w-14" />
          </div>
          <StopColumn seg={last} />
        </div>
      ) : (
        <div className="mx-auto w-full max-w-3xl">
          {/* Узкий экран: короткая вертикаль */}
          <div className="relative flex flex-col items-center py-0.5 sm:hidden">
            <div
              className="pointer-events-none absolute bottom-9 left-1/2 top-1 w-px -translate-x-1/2 bg-gradient-to-b from-gray-200 via-gray-300/60 to-gray-200 dark:from-gray-800 dark:via-gray-600/60 dark:to-gray-800"
              aria-hidden
            />
            <div className="relative z-[1] flex flex-col items-center gap-1.5">
              <StopColumn dense seg={first} />
              <StopColumn dense seg={mid} muted />
              {hiddenBetween > 0 ? (
                <p className="py-0.5 text-center text-[10px] text-gray-500 dark:text-gray-400">
                  ещё {hiddenBetween} не показано
                </p>
              ) : null}
              <StopColumn dense seg={last} />
            </div>
          </div>

          {/* sm+: один ряд — низкая «лента» под строку таблицы */}
          <div className="relative hidden py-0.5 sm:block">
            <div className="flex flex-nowrap items-start justify-center gap-x-1.5 md:gap-x-4">
              <div className="min-w-0 flex-[1_1_0] max-w-[10.5rem]">
                <StopColumn dense seg={first} />
              </div>
              <div
                className="mt-2.5 flex shrink-0 items-center self-start"
                aria-hidden
              >
                <div className="h-px w-5 bg-gray-300/90 dark:bg-gray-700 md:w-10" />
              </div>
              <div className="min-w-0 flex-[1_1_0] max-w-[10.5rem]">
                <StopColumn dense seg={mid} muted />
              </div>
              <div
                className="mt-2.5 flex shrink-0 items-center self-start"
                aria-hidden
              >
                <div className="h-px w-5 bg-gray-300/90 dark:bg-gray-700 md:w-10" />
              </div>
              <div className="min-w-0 flex-[1_1_0] max-w-[10.5rem]">
                <StopColumn dense seg={last} />
              </div>
            </div>
            {hiddenBetween > 0 ? (
              <p className="mt-1 text-center text-[10px] text-gray-500 dark:text-gray-400">
                ещё {hiddenBetween} не показано
              </p>
            ) : null}
          </div>

          {showExpand ? (
            <motion.div
              className="mt-1 flex justify-center sm:mt-1"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.04, duration: 0.2 }}
            >
              <button
                type="button"
                onClick={() => setExpanded(true)}
                className="rounded-md px-2.5 py-1 text-[11px] font-medium text-blue-600/95 transition-colors hover:bg-blue-500/10 dark:text-blue-400 dark:hover:bg-blue-400/10"
              >
                Полный маршрут · {segments.length}
              </button>
            </motion.div>
          ) : null}
        </div>
      )}
    </>
  );

  return (
    <div className={shell}>
      <div className="mx-auto w-full max-w-xl">
        <div className="mb-1 flex items-center justify-between gap-2 px-0.5">
          <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-gray-400 dark:text-gray-500">
            Маршрут
          </span>
          {expanded && hasMiddle ? (
            <button
              type="button"
              onClick={() => setExpanded(false)}
              className="shrink-0 text-[11px] font-medium text-blue-600/90 hover:underline dark:text-blue-400/95"
            >
              Свернуть
            </button>
          ) : null}
        </div>

        <div className="relative overflow-hidden">
          <AnimatePresence mode="wait" initial={false}>
            {expanded && hasMiddle ? (
              <motion.div
                key="route-expanded"
                role="region"
                aria-label="Полный маршрут"
                initial={{ opacity: 0, y: 8, filter: "blur(6px)" }}
                animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                exit={{ opacity: 0, y: -6, filter: "blur(4px)" }}
                transition={{ duration: 0.3, ease: easeSmooth }}
              >
                <TimelineRiver segments={segments} />
              </motion.div>
            ) : (
              <motion.div
                key="route-collapsed"
                initial={{ opacity: 0, y: -6, filter: "blur(4px)" }}
                animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                exit={{ opacity: 0, y: 8, filter: "blur(6px)" }}
                transition={{ duration: 0.28, ease: easeSmooth }}
              >
                {collapseSummary}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};

export default AttendanceAreaSequenceMap;
