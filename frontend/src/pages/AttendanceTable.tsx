import React from "react";
import { AttendanceData } from "../schemas/IData";
import { formatDate, formatMinutes, formatDateFromKeyRu } from "../utils/utils";
import { motion } from "framer-motion";

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
    boxShadow: "0 0 8px rgba(0,0,0,0.7)",
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
  const defaultText = "";

  const getStatusStyle = (data: AttendanceData) => {
    const hasInOut = data.first_in && data.last_out;

    if (data.is_remote_work) {
      return {
        bg: "bg-sky-200 dark:bg-sky-800",
        text: "text-sky-600 dark:text-sky-300",
        border: "border-sky-200 dark:border-sky-700",
        hoverBg: "hover:bg-sky-100 dark:hover:bg-sky-700",
      };
    } else if (data.absent_reason && data.absent_reason.trim() !== "") {
      return data.is_absent_approved
        ? {
            bg: "bg-violet-200 dark:bg-violet-800",
            text: "text-violet-600 dark:text-violet-300",
            border: "border-violet-200 dark:border-violet-700",
            hoverBg: "hover:bg-violet-300 dark:hover:bg-violet-700",
          }
        : {
            bg: "bg-rose-200 dark:bg-rose-800",
            text: "text-rose-600 dark:text-rose-300",
            border: "border-rose-200 dark:border-rose-700",
            hoverBg: "hover:bg-rose-300 dark:hover:bg-rose-700",
          };
    } else if (data.is_weekend) {
      return hasInOut
        ? {
            bg: "bg-green-200 dark:bg-green-800",
            text: "text-green-600 dark:text-green-300",
            border: "border-green-200 dark:border-green-700",
            hoverBg: "hover:bg-green-300 dark:hover:bg-green-700",
          }
        : {
            bg: "bg-amber-200 dark:bg-amber-800",
            text: "text-amber-600 dark:text-amber-300",
            border: "border-amber-200 dark:border-amber-700",
            hoverBg: "hover:bg-amber-300 dark:hover:bg-amber-700",
          };
    } else if (!hasInOut) {
      return {
        bg: "bg-red-200 dark:bg-red-800",
        text: "text-red-600 dark:text-red-300",
        border: "border-red-200 dark:border-red-700",
        hoverBg: "hover:bg-red-300 dark:hover:bg-red-700",
      };
    }
    return {
      bg: "bg-white dark:bg-gray-800",
      text: "text-gray-600 dark:text-gray-300",
      border: "border-gray-200 dark:border-gray-700",
      hoverBg: "hover:bg-gray-300 dark:hover:bg-gray-700",
    };
  };

  const getStatusText = (data: AttendanceData) => {
    const {
      first_in,
      last_out,
      is_weekend,
      is_remote_work,
      is_absent_approved,
      absent_reason,
    } = data;
    const hasInOut = first_in && last_out;

    if (is_remote_work) {
      return "Дистанционная работа";
    }
    if (absent_reason && absent_reason.trim() !== "") {
      return (
        "Отсутствует (" +
        (is_absent_approved ? "Одобрено" : "Не одобрено") +
        ")"
      );
    }
    if (is_weekend) {
      return hasInOut ? "Работа в выходной" : "Выходной день";
    }
    if (!hasInOut) return defaultText;
    return "Рабочий день";
  };

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
    <div className="hidden md:block w-full">
      <div className="rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="text-black dark:text-white">
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
          <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
            {Object.entries(attendance)
              .reverse()
              .map(([date, data], idx) => {
                const status = getStatusStyle(data);
                const statusText = getStatusText(data);

                return (
                  <motion.tr
                    key={date}
                    className={
                      "transition-colors duration-200 " +
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
    idx: number
  ) => {
    const status = getStatusStyle(data);
    const statusText = getStatusText(data);

    return (
      <motion.div
        key={date}
        className={
          "rounded-lg shadow-sm " + status.bg + " border " + status.border
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
        </div>
      </motion.div>
    );
  };

  return (
    <div className="w-full">
      {renderDesktopTable()}

      <div className="block md:hidden">
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
