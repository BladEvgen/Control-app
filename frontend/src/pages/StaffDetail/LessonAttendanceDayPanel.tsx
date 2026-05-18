import React from "react";
import { formatDate } from "../../utils/utils";
import type { LessonAttendanceDayAudit } from "../../schemas/IData";

type Props = {
  day: LessonAttendanceDayAudit;
  compact?: boolean;
  embedded?: boolean;
};

function lessonMark(lesson: LessonAttendanceDayAudit["lessons"][0]): string {
  if (lesson.fraud_attempt) return "×";
  if (lesson.awaits_manual_review) return "?";
  return "";
}

const LessonAttendanceDayPanel: React.FC<Props> = ({
  day,
  compact,
  embedded = false,
}) => {
  const showSummary = Boolean(day.summary_ru?.trim());
  const wrap =
    compact && embedded
      ? "space-y-2"
      : compact
        ? "mt-3 rounded-lg border border-gray-200/80 bg-gray-50/60 px-3 py-2.5 dark:border-gray-700/90 dark:bg-gray-900/35"
        : "rounded-lg border border-gray-200 bg-gray-50/30 p-3 dark:border-gray-800 dark:bg-gray-950/40";

  return (
    <div className={wrap}>
      {showSummary ? (
        <p
          className={
            compact
              ? day.lesson_day_status === "rejected_fraud"
                ? "mb-2 text-[11px] leading-snug text-rose-700/95 dark:text-rose-400/90"
                : day.lesson_day_status === "pending_manual_review"
                  ? "mb-2 text-[11px] leading-snug text-amber-900/80 dark:text-amber-400/85"
                  : "mb-2 text-[11px] leading-snug text-gray-600 dark:text-gray-400"
              : day.lesson_day_status === "rejected_fraud"
                ? "mb-2 text-[12px] leading-snug text-rose-700 dark:text-rose-400"
                : day.lesson_day_status === "pending_manual_review"
                  ? "mb-2 text-[12px] leading-snug text-amber-900/85 dark:text-amber-400/90"
                  : "mb-2 text-[12px] leading-snug text-gray-600 dark:text-gray-400"
          }
        >
          {day.summary_ru}
        </p>
      ) : null}

      {day.lessons.length > 0 ? (
        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-gray-400 dark:text-gray-500">
          Занятия
        </p>
      ) : null}

      <ul className="m-0 list-none space-y-2 p-0">
        {day.lessons.map((lesson) => {
          const mark = lessonMark(lesson);
          const t0 = lesson.first_in ? formatDate(lesson.first_in) : null;
          const t1 = lesson.last_out ? formatDate(lesson.last_out) : null;
          const time =
            t0 || t1 ? (t0 && t1 ? `${t0}–${t1}` : t0 || t1 || "") : null;

          const edge = lesson.fraud_attempt
            ? "border-l-rose-500/90"
            : lesson.awaits_manual_review
              ? "border-l-amber-400/90"
              : "border-l-sky-500/50 dark:border-l-sky-500/40";

          return (
            <li
              key={lesson.lesson_attendance_id}
              className={
                "rounded-md border border-gray-200/80 bg-white/80 py-2 pl-2.5 pr-2.5 shadow-sm dark:border-gray-800 dark:bg-gray-950/50 " +
                "border-l-[3px] " +
                edge
              }
            >
              <div className="flex flex-col gap-1.5 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
                <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
                  {mark ? (
                    <span
                      className={
                        "inline-flex size-5 shrink-0 items-center justify-center rounded text-xs font-bold " +
                        (lesson.fraud_attempt
                          ? "bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300"
                          : "bg-amber-100 text-amber-900 dark:bg-amber-950/50 dark:text-amber-300")
                      }
                      title={
                        lesson.fraud_attempt ? "Не в отчёте" : "На проверке"
                      }
                    >
                      {mark}
                    </span>
                  ) : null}
                  {time ? (
                    <span className="font-mono text-[11px] tabular-nums text-gray-600 dark:text-gray-400">
                      {time}
                    </span>
                  ) : null}
                </div>
                <p className="min-w-0 flex-1 text-[12px] font-medium leading-snug text-gray-900 dark:text-gray-100 sm:text-right sm:pl-2">
                  {lesson.subject_name || "Занятие"}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default LessonAttendanceDayPanel;
