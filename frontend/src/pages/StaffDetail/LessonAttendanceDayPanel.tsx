import React from "react";
import { motion } from "framer-motion";
import { formatDate } from "../../utils/utils";
import type {
  LessonAttendanceAuditLesson,
  LessonAttendanceDayAudit,
  LessonBridge,
  LessonBridgeReason,
} from "../../schemas/IData";

type Props = {
  day: LessonAttendanceDayAudit;
  compact?: boolean;
  embedded?: boolean;
};

const easeSmooth = [0.22, 1, 0.36, 1] as const;

const BRIDGE_REASON: Record<LessonBridgeReason, string> = {
  photo: "фото не подтверждено",
  place: "нет координат",
};

const durationRu = (minutes: number): string => {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h ? (m ? `${h} ч ${m} мин` : `${h} ч`) : `${m} мин`;
};

function lessonState(lesson: LessonAttendanceAuditLesson) {
  if (lesson.fraud_attempt)
    return {
      label: "Не в отчёте",
      dot: "bg-rose-500 shadow-[0_0_0_3px] shadow-rose-500/15 dark:bg-rose-400",
    };
  if (lesson.awaits_manual_review)
    return {
      label: "На проверке",
      dot: "bg-amber-500 shadow-[0_0_0_3px] shadow-amber-500/15 dark:bg-amber-400",
    };
  return {
    label: "Отметка",
    dot: "bg-emerald-500 shadow-[0_0_0_3px] shadow-emerald-500/15 dark:bg-emerald-400",
  };
}

function LessonStop({ lesson }: { lesson: LessonAttendanceAuditLesson }) {
  const state = lessonState(lesson);
  const t0 = lesson.first_in ? formatDate(lesson.first_in) : null;
  const t1 = lesson.last_out ? formatDate(lesson.last_out) : null;
  const time = t0 && t1 ? `${t0}–${t1}` : t0 || t1 || "";
  const place = lesson.location_name || "Точка не найдена";

  return (
    <div className="flex min-w-0 max-w-[10.5rem] flex-col items-center text-center">
      <span
        className={`size-2 shrink-0 rounded-full ${state.dot}`}
        title={state.label}
      />
      <span className="mt-1.5 font-mono text-[10px] tabular-nums text-gray-500 dark:text-gray-400">
        {time}
      </span>
      <span className="text-[9px] font-medium uppercase tracking-[0.12em] text-gray-400 dark:text-gray-500">
        {state.label}
      </span>
      <span
        className="mt-0.5 line-clamp-2 w-full text-[10px] leading-snug text-gray-800 dark:text-gray-200 sm:text-[11px]"
        title={place}
      >
        {place}
      </span>
      {lesson.subject_name ? (
        <span
          className="line-clamp-1 w-full text-[10px] text-gray-500 dark:text-gray-400"
          title={lesson.subject_name}
        >
          {lesson.subject_name}
        </span>
      ) : null}
    </div>
  );
}

function Bridge({ bridge }: { bridge?: LessonBridge | null }) {
  if (!bridge) return null;
  const gap = bridge.gap_seconds / 60;
  const travel = bridge.travel_seconds / 60;
  const credited = bridge.credited_seconds / 60;
  const has = credited >= 1;
  const full = has && credited >= gap - travel - 1;
  const caption = has
    ? full
      ? `+${durationRu(credited)}`
      : `+${durationRu(credited)} из ${durationRu(gap)}`
    : bridge.reason
      ? BRIDGE_REASON[bridge.reason]
      : travel >= gap && gap >= 1
        ? "дорога дольше перерыва"
        : "";
  const details = [
    `Между отметками ${durationRu(gap)}`,
    travel >= 1 ? `дорога в другой корпус ~${durationRu(travel)}` : "",
    has && !full ? "долгий промежуток без отметок засчитан частично" : "",
    has ? `засчитано ${durationRu(credited)}` : `не засчитано: ${caption}`,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <div
      className="flex shrink-0 flex-col items-center gap-1 self-center sm:mt-[3px] sm:self-start"
      title={details}
    >
      <span
        className={
          "block h-5 w-px sm:h-px sm:w-14 " +
          (has
            ? full
              ? "bg-emerald-500/70 dark:bg-emerald-400/60"
              : "bg-gradient-to-b from-emerald-500/70 to-gray-300 sm:bg-gradient-to-r dark:to-gray-600"
            : "border-l border-dashed border-gray-300 sm:border-l-0 sm:border-t dark:border-gray-600")
        }
        aria-hidden
      />
      <span
        className={
          "whitespace-nowrap text-[10px] " +
          (has
            ? "font-medium text-emerald-700 dark:text-emerald-400"
            : "text-gray-400 dark:text-gray-500")
        }
      >
        {caption}
      </span>
      {travel >= 1 ? (
        <span className="whitespace-nowrap text-[9px] text-gray-400 dark:text-gray-500">
          дорога ~{durationRu(travel)}
        </span>
      ) : null}
    </div>
  );
}

const LessonAttendanceDayPanel: React.FC<Props> = ({
  day,
  compact,
  embedded = false,
}) => {
  const lessons = day.lessons;
  const shell = embedded
    ? "w-full overflow-x-hidden"
    : "mt-1.5 w-full max-w-full overflow-x-hidden rounded-2xl border border-gray-200/55 bg-white/40 px-3 py-3 shadow-sm dark:border-gray-800/70 dark:bg-gray-950/35 sm:px-4";
  const summaryTone =
    day.lesson_day_status === "rejected_fraud"
      ? "text-rose-700 dark:text-rose-400"
      : day.lesson_day_status === "pending_manual_review"
        ? "text-amber-900/85 dark:text-amber-400/90"
        : "text-gray-600 dark:text-gray-400";

  return (
    <div className={shell}>
      <div className="mx-auto w-full max-w-xl">
        <div className="mb-1 flex items-center justify-between gap-2 px-0.5">
          <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-gray-400 dark:text-gray-500">
            Занятия
          </span>
          {day.credited_seconds ? (
            <span className="text-[11px] font-medium text-gray-700 dark:text-gray-300">
              Засчитано {durationRu(day.credited_seconds / 60)}
            </span>
          ) : null}
        </div>

        {day.summary_ru?.trim() ? (
          <p
            className={
              (compact ? "text-[11px] " : "text-[12px] ") +
              "mb-2 px-0.5 leading-snug " +
              summaryTone
            }
          >
            {day.summary_ru}
          </p>
        ) : null}

        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.28, ease: easeSmooth }}
          className="flex flex-col items-center gap-1.5 py-0.5 sm:flex-row sm:flex-wrap sm:items-start sm:justify-center sm:gap-x-2 sm:gap-y-3"
        >
          {lessons.map((lesson, i) => (
            <React.Fragment key={lesson.lesson_attendance_id}>
              {i > 0 ? <Bridge bridge={lessons[i - 1].bridge_to_next} /> : null}
              <LessonStop lesson={lesson} />
            </React.Fragment>
          ))}
        </motion.div>
      </div>
    </div>
  );
};

export default LessonAttendanceDayPanel;
