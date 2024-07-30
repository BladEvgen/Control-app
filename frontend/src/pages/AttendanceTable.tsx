import React from "react";
import { AttendanceData } from "../schemas/IData";
import { formatDate, formatMinutes } from "../utils/utils";

interface AttendanceTableProps {
  attendance: Record<string, AttendanceData>;
}

const AttendanceTable: React.FC<AttendanceTableProps> = ({ attendance }) => {
  const renderAttendanceRow = (
    date: string,
    data: AttendanceData,
    isFirst: boolean,
    isLast: boolean
  ) => {
    const isWeekend = data.is_weekend;
    const hasInOut = data.first_in && data.last_out;

    const rowClassNames = `px-6 py-3 whitespace-nowrap ${
      isFirst ? "rounded-t-lg" : ""
    } ${isLast ? "rounded-b-lg" : ""}`;

    if (!hasInOut && !isWeekend) {
      return (
        <tr key={date} className="bg-red-200 dark:bg-red-700 dark:text-white">
          <td colSpan={5} className={`${rowClassNames}`}>
            <div className="flex flex-col md:flex-row md:justify-center">
              <span className="text-left">{date}</span>
              <span className="ml-4 md:ml-0 md:w-full md:text-center">
                Нет данных
              </span>
            </div>
          </td>
        </tr>
      );
    } else if (!hasInOut && isWeekend) {
      return (
        <tr
          key={date}
          className="bg-yellow-200 dark:bg-yellow-700 dark:text-white"
        >
          <td colSpan={5} className={`${rowClassNames}`}>
            <div className="flex flex-col md:flex-row md:justify-center">
              <span className="text-left">{date}</span>
              <span className="ml-4 md:ml-0 md:w-full md:text-center">
                Выходной день
              </span>
            </div>
          </td>
        </tr>
      );
    } else {
      return (
        <tr
          key={date}
          className={
            isWeekend
              ? "bg-green-200 dark:bg-green-700 dark:text-white"
              : "dark:text-gray-400"
          }
        >
          <td className={rowClassNames}>{date}</td>
          <td className={rowClassNames}>
            {data.first_in ? formatDate(data.first_in) : "Нет данных"}
          </td>
          <td className={rowClassNames}>
            {data.last_out ? formatDate(data.last_out) : "Нет данных"}
          </td>
          <td className={rowClassNames}>{data.percent_day}%</td>
          <td className={rowClassNames}>
            {data.total_minutes
              ? formatMinutes(data.total_minutes)
              : "Нет данных"}
          </td>
        </tr>
      );
    }
  };

  return (
    <div className="overflow-x-auto">
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
            .map(([date, data], index, array) =>
              renderAttendanceRow(
                date,
                data,
                index === 0,
                index === array.length - 1
              )
            )}
        </tbody>
      </table>
    </div>
  );
};

export default AttendanceTable;
