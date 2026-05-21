import React, { Fragment } from "react";
import { AttendanceData } from "../schemas/IData";
import { resolveStaffAttendanceDayVisual } from "../utils/attendanceDayPresentation";
import { formatDate, formatMinutes, formatDateFromKeyRu } from "../utils/utils";
import { motion } from "framer-motion";
import AttendanceAreaSequenceMap from "./StaffDetail/AttendanceAreaSequenceMap";
import LessonAttendanceDayPanel from "./StaffDetail/LessonAttendanceDayPanel";

interface AttendanceTableProps {
  attendance: Record<string, AttendanceData>;
}

const rowVariants = {
  hidden: { opacity: 0, x: 20 },
  visible: (i: number) => ({
    opacity: 1,
    x: 0,
    transition: { delay: i * 0.04, duration: 0.4 },
  }),
  hover: {
    boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
    transformOrigin: "center center",
  },
  tap: { scale: 0.995, transformOrigin: "center center" },
};

const cardVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.04, duration: 0.4 },
  }),
  hover: {
    scale: 1.01,
    transformOrigin: "center center",
  },
  tap: { scale: 0.99, transformOrigin: "center center" },
};

const AttendanceTable: React.FC<AttendanceTableProps> = ({ attendance }) => {
  const renderTime = (time: string | undefined) => {
    return time ? formatDate(time) : "";
  };

  const renderTotalTime = (data: AttendanceData) => {
    if (data.total_minutes !== undefined && data.total_minutes > 0) {
      return formatMinutes(data.total_minutes);
    }
    return "";
  };

  const renderProgressBar = (data: AttendanceData) => {
    if (data.is_weekend) return null;
    return (
      <div className="flex items-center">
        <div className="w-16 bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
          <div
            className="bg-blue-600 dark:bg-blue-400 h-full rounded-full transition-all duration-300"
            style={{ width: data.percent_day + "%" }}
          />
        </div>
        <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">
          {data.percent_day}%
        </span>
      </div>
    );
  };

  const renderDesktopTable = () => (
    <div className="hidden lg:block w-full min-w-0">
      <div className="data-table-wrap overflow-x-auto rounded-lg border border-gray-200 shadow-sm dark:border-gray-800">
        <table className="min-w-full w-full">
          <thead>
            <tr className="bg-gray-50 text-black dark:bg-gray-900 dark:text-white">
              {[
                "Дата",
                "Первое прибытие",
                "Последний уход",
                "Процент дня",
                "Всего времени (Ч:М)",
              ].map((header) => (
                <th
                  key={header}
                  scope="col"
                  className="px-6 py-4 text-left text-sm font-semibold uppercase tracking-wide"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
            {Object.entries(attendance)
              .reverse()
              .map(([date, data], idx) => {
                const visual = resolveStaffAttendanceDayVisual(data);
                const status = visual.rowStyle;
                const statusText = visual.rowStatusText;
                const lessonDay = data.lesson_attendance_day;
                const hasZones =
                  Array.isArray(data.area_sequence) &&
                  data.area_sequence.length > 0;

                return (
                  <Fragment key={date}>
                    <motion.tr
                      className={
                        "transition-colors duration-200 " +
                        status.borderLeft +
                        " " +
                        status.bg +
                        " " +
                        status.hoverBg
                      }
                      variants={rowVariants}
                      initial="hidden"
                      animate="visible"
                      whileHover="hover"
                      whileTap="tap"
                      custom={idx}
                    >
                      <td className="px-6 py-4">
                        <div className="flex flex-col">
                          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                            {formatDateFromKeyRu(date)}
                          </span>
                          <span className={"text-xs mt-1 " + status.text}>
                            {statusText}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-700 dark:text-gray-300">
                        {renderTime(data.first_in ?? undefined)}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-700 dark:text-gray-300">
                        {renderTime(data.last_out ?? undefined)}
                      </td>
                      <td className="px-6 py-4">{renderProgressBar(data)}</td>
                      <td className="px-6 py-4 text-sm text-gray-700 dark:text-gray-300">
                        {renderTotalTime(data)}
                      </td>
                    </motion.tr>
                    {lessonDay || hasZones ? (
                      <tr className="border-t border-gray-100 bg-white dark:border-gray-800 dark:bg-gray-950">
                        <td
                          className={"px-6 pb-4 pt-2 " + status.borderLeft}
                          colSpan={5}
                        >
                          <div className="mx-auto max-w-2xl">
                            <div className="rounded-2xl border border-gray-200/60 bg-gradient-to-b from-gray-50/90 to-white/30 px-3 py-3 shadow-sm dark:border-gray-800/80 dark:from-gray-900/50 dark:to-gray-950/20 sm:px-4">
                              {lessonDay ? (
                                <LessonAttendanceDayPanel
                                  day={lessonDay}
                                  compact
                                  embedded
                                />
                              ) : null}
                              {lessonDay && hasZones ? (
                                <div
                                  className="my-3 h-px w-full bg-gradient-to-r from-transparent via-gray-200/90 to-transparent dark:via-gray-700/80"
                                  aria-hidden
                                />
                              ) : null}
                              {hasZones ? (
                                <AttendanceAreaSequenceMap
                                  areaSequence={data.area_sequence}
                                  embedded
                                />
                              ) : null}
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
          </tbody>
        </table>
      </div>
    </div>
  );

  const renderMobileCard = (
    date: string,
    data: AttendanceData,
    idx: number,
  ) => {
    const visual = resolveStaffAttendanceDayVisual(data);
    const status = visual.rowStyle;
    const statusText = visual.rowStatusText;
    const lessonDay = data.lesson_attendance_day;
    const hasZones =
      Array.isArray(data.area_sequence) && data.area_sequence.length > 0;

    return (
      <motion.div
        key={date}
        className={
          "rounded-lg border shadow-sm " +
          status.bg +
          " " +
          status.border +
          " " +
          status.borderLeft
        }
        variants={cardVariants}
        initial="hidden"
        animate="visible"
        whileHover="hover"
        whileTap="tap"
        custom={idx}
      >
        <div className="p-4">
          <div className="flex justify-between items-start mb-3">
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
              {formatDateFromKeyRu(date)}
            </span>
            <span className={"text-xs font-medium " + status.text}>
              {statusText}
            </span>
          </div>

          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600 dark:text-gray-400">
                Процент дня
              </span>
              {!data.is_weekend && renderProgressBar(data)}
            </div>

            {data.first_in && (
              <div className="flex justify-between">
                <span className="text-sm text-gray-600 dark:text-gray-400">
                  Прибытие
                </span>
                <span className="text-sm text-gray-900 dark:text-gray-100">
                  {renderTime(data.first_in)}
                </span>
              </div>
            )}

            {data.last_out && (
              <div className="flex justify-between">
                <span className="text-sm text-gray-600 dark:text-gray-400">
                  Уход
                </span>
                <span className="text-sm text-gray-900 dark:text-gray-100">
                  {renderTime(data.last_out)}
                </span>
              </div>
            )}

            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-400">
                Всего времени
              </span>
              <span className="text-sm text-gray-900 dark:text-gray-100">
                {renderTotalTime(data)}
              </span>
            </div>
          </div>
          {lessonDay || hasZones ? (
            <div className="mt-4">
              <div className="mx-auto max-w-2xl rounded-2xl border border-gray-200/60 bg-gradient-to-b from-gray-50/90 to-white/30 px-3 py-3 shadow-sm dark:border-gray-800/80 dark:from-gray-900/50 dark:to-gray-950/20">
                {lessonDay ? (
                  <LessonAttendanceDayPanel day={lessonDay} compact embedded />
                ) : null}
                {lessonDay && hasZones ? (
                  <div
                    className="my-3 h-px w-full bg-gradient-to-r from-transparent via-gray-200/90 to-transparent dark:via-gray-700/80"
                    aria-hidden
                  />
                ) : null}
                {hasZones ? (
                  <AttendanceAreaSequenceMap
                    areaSequence={data.area_sequence}
                    embedded
                  />
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      </motion.div>
    );
  };

  return (
    <div className="w-full">
      {renderDesktopTable()}

      <div className="block lg:hidden">
        <div className="grid grid-cols-1 gap-4">
          {Object.entries(attendance)
            .reverse()
            .map(([date, data], idx) => renderMobileCard(date, data, idx))}
        </div>
      </div>
    </div>
  );
};

export default AttendanceTable;
