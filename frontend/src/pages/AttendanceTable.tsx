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
  tap: { scale: 0.99, transformOrigin: "center center" },
};

const cardVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.04, duration: 0.4 },
  }),
  hover: {
    scale: 1.001,
    transformOrigin: "center center",
  },
  tap: { scale: 0.99, transformOrigin: "center center" },
};

const AttendanceTable: React.FC<AttendanceTableProps> = ({ attendance }) => {
  const defaultText = "Отсутствует (Не одобрено)";

  const renderAttendanceRow = (
    date: string,
    data: AttendanceData,
    rowIndex: number,
    isFirst: boolean,
    isLast: boolean
  ) => {
    const {
      first_in,
      last_out,
      is_weekend,
      is_remote_work,
      is_absent_approved,
      absent_reason,
    } = data;
    const hasInOut = first_in && last_out;
    const rowClassNames = `px-6 py-3 whitespace-nowrap
      ${isFirst ? "rounded-t-lg" : ""} 
      ${isLast ? "rounded-b-lg" : ""}`;

    let bgColor = "";
    let statusText = "";

    if (is_remote_work) {
      bgColor = "bg-sky-200 dark:bg-sky-700";
      statusText = "Дистанционная работа";
    } else if (absent_reason && absent_reason.trim() !== "") {
      bgColor = is_absent_approved
        ? "bg-violet-200 dark:bg-violet-700"
        : "bg-rose-200 dark:bg-rose-700";
      statusText = `Отсутствует (${absent_reason})`;
      if (hasInOut) {
        statusText += ` (Прибытие: ${formatDate(first_in)}, Уход: ${formatDate(
          last_out
        )})`;
      }
    } else if (is_weekend) {
      if (hasInOut) {
        bgColor = "bg-green-200 dark:bg-green-700";
        statusText = `Работа в выходной (Прибытие: ${formatDate(
          first_in
        )}, Уход: ${formatDate(last_out)})`;
      } else {
        bgColor = "bg-amber-200 dark:bg-amber-700";
        statusText = "Выходной день";
      }
    } else if (!hasInOut) {
      bgColor = "bg-red-200 dark:bg-red-700";
      statusText = defaultText;
    } else {
      bgColor = "bg-white dark:bg-gray-800";
      statusText = `Рабочий день (Прибытие: ${formatDate(
        first_in
      )}, Уход: ${formatDate(last_out)})`;
    }

    return (
      <motion.tr
        key={date}
        className={`${bgColor} dark:text-white`}
        variants={rowVariants}
        initial="hidden"
        animate="visible"
        whileHover="hover"
        whileTap="tap"
        custom={rowIndex}
      >
        <td colSpan={5} className={rowClassNames}>
          <div className="flex flex-col md:flex-row md:justify-center">
            <span className="text-left">{formatDateFromKeyRu(date)}</span>
            <span className="ml-4 md:ml-0 md:w-full md:text-center">
              {statusText}
            </span>
          </div>
        </td>
      </motion.tr>
    );
  };

  const renderAttendanceDataRow = (
    date: string,
    data: AttendanceData,
    rowIndex: number,
    isFirst: boolean,
    isLast: boolean
  ) => {
    const rowClassNames = `px-6 py-3 whitespace-nowrap
      ${isFirst ? "rounded-t-lg" : ""}
      ${isLast ? "rounded-b-lg" : ""}`;

    return (
      <motion.tr
        key={date}
        className="dark:text-gray-400"
        variants={rowVariants}
        initial="hidden"
        animate="visible"
        whileHover="hover"
        whileTap="tap"
        custom={rowIndex}
      >
        <td className={rowClassNames}>{formatDateFromKeyRu(date)}</td>
        <td className={rowClassNames}>
          {data.first_in ? formatDate(data.first_in) : defaultText}
        </td>
        <td className={rowClassNames}>
          {data.last_out ? formatDate(data.last_out) : defaultText}
        </td>
        <td className={rowClassNames}>{data.percent_day}%</td>
        <td className={rowClassNames}>
          {data.total_minutes ? formatMinutes(data.total_minutes) : defaultText}
        </td>
      </motion.tr>
    );
  };

  const renderAttendanceRowConditional = (
    date: string,
    data: AttendanceData,
    rowIndex: number,
    isFirst: boolean,
    isLast: boolean
  ) => {
    const hasInOut = data.first_in && data.last_out;
    const isWeekend = data.is_weekend;

    if (
      !hasInOut ||
      isWeekend ||
      (data.absent_reason && data.absent_reason.trim() !== "")
    ) {
      return renderAttendanceRow(date, data, rowIndex, isFirst, isLast);
    } else {
      return renderAttendanceDataRow(date, data, rowIndex, isFirst, isLast);
    }
  };

  const renderAttendanceCard = (
    date: string,
    data: AttendanceData,
    cardIndex: number
  ) => {
    const {
      first_in,
      last_out,
      is_weekend,
      is_remote_work,
      is_absent_approved,
      absent_reason,
    } = data;
    const hasInOut = first_in && last_out;
    const isNoData = !hasInOut;

    let detailFirstIn = "";
    let detailLastOut = "";
    let detailTotalMinutes = "";

    let cardBgColor = "";
    let statusText = "";

    if (is_remote_work) {
      cardBgColor = "bg-sky-100 dark:bg-sky-700";
      statusText = "Дистанционная работа";
      detailFirstIn = first_in ? formatDate(first_in) : "";
      detailLastOut = last_out ? formatDate(last_out) : "";
      detailTotalMinutes = data.total_minutes
        ? formatMinutes(data.total_minutes)
        : "";
    } else if (absent_reason && absent_reason.trim() !== "") {
      cardBgColor = is_absent_approved
        ? "bg-violet-100 dark:bg-violet-700"
        : "bg-rose-100 dark:bg-rose-700";
      statusText = `Отсутствует (${
        is_absent_approved ? "Одобрено" : "Не одобрено"
      })`;
      detailFirstIn = first_in ? formatDate(first_in) : "";
      detailLastOut = last_out ? formatDate(last_out) : "";
      detailTotalMinutes = data.total_minutes
        ? formatMinutes(data.total_minutes)
        : "";
    } else if (is_weekend) {
      if (hasInOut) {
        cardBgColor = "bg-green-100 dark:bg-green-700";
        statusText = "Работа в выходной";
        detailFirstIn = formatDate(first_in);
        detailLastOut = formatDate(last_out);
        detailTotalMinutes = data.total_minutes
          ? formatMinutes(data.total_minutes)
          : "";
      } else {
        cardBgColor = "bg-amber-100 dark:bg-amber-700";
        statusText = "Выходной день";
      }
    } else if (isNoData) {
      cardBgColor = "bg-red-100 dark:bg-red-700";
      statusText = "Отсутствует (Не одобрено)";
    } else {
      cardBgColor = "bg-white dark:bg-gray-800";
      detailFirstIn = formatDate(first_in);
      detailLastOut = formatDate(last_out);
      detailTotalMinutes = data.total_minutes
        ? formatMinutes(data.total_minutes)
        : "";
      statusText = "Рабочий день";
    }

    return (
      <motion.div
        key={date}
        className={`p-4 rounded-lg shadow-md mb-4 ${cardBgColor}`}
        variants={cardVariants}
        initial="hidden"
        animate="visible"
        whileHover="hover"
        whileTap="tap"
        custom={cardIndex}
      >
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm font-medium text-gray-900 dark:text-white">
            {formatDateFromKeyRu(date)}
          </span>
          <span
            className={`text-xs font-semibold ${
              is_remote_work
                ? "text-sky-600 dark:text-sky-300"
                : absent_reason && absent_reason.trim() !== ""
                ? is_absent_approved
                  ? "text-violet-600 dark:text-violet-300"
                  : "text-rose-600 dark:text-rose-300"
                : is_weekend && hasInOut
                ? "text-green-600 dark:text-green-300"
                : is_weekend
                ? "text-amber-600 dark:text-amber-300"
                : "text-gray-600 dark:text-gray-400"
            }`}
          >
            {statusText}
          </span>
        </div>
        <div className="flex flex-col space-y-1 text-sm text-gray-700 dark:text-gray-300">
          <div className="flex justify-between">
            <span>Первое прибытие:</span>
            <span>{detailFirstIn}</span>
          </div>
          <div className="flex justify-between">
            <span>Последний уход:</span>
            <span>{detailLastOut}</span>
          </div>
          <div className="flex justify-between">
            <span>Процент дня:</span>
            <span>{data.percent_day}%</span>
          </div>
          <div className="flex justify-between">
            <span>Всего времени:</span>
            <span>{detailTotalMinutes}</span>
          </div>
        </div>
      </motion.div>
    );
  };

  return (
    <div className="overflow-x-auto overflow-y-hidden">
      {/* Для больших экранов */}
      <div className="hidden md:block">
        <table className="w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th
                scope="col"
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400"
              >
                Дата
              </th>
              <th
                scope="col"
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400"
              >
                Первое прибытие
              </th>
              <th
                scope="col"
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400"
              >
                Последний уход
              </th>
              <th
                scope="col"
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400"
              >
                Процент дня
              </th>
              <th
                scope="col"
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400"
              >
                Всего времени (Ч:М)
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200 dark:bg-gray-900 dark:divide-gray-700">
            {Object.entries(attendance)
              .reverse()
              .map(([date, data], idx, array) =>
                renderAttendanceRowConditional(
                  date,
                  data,
                  idx,
                  idx === 0,
                  idx === array.length - 1
                )
              )}
          </tbody>
        </table>
      </div>
      {/* Для мобильных устройств */}
      <div className="block md:hidden">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Object.entries(attendance)
            .reverse()
            .map(([date, data], idx) => renderAttendanceCard(date, data, idx))}
        </div>
      </div>
    </div>
  );
};

export default AttendanceTable;
