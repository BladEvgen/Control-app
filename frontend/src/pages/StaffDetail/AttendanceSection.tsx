import React from "react";
import DateForm from "../DateForm";
import AttendanceTable from "../AttendanceTable";
import { formatDateRu, declensionDays } from "../../utils/utils";
import { FiInfo } from "react-icons/fi";
import { motion } from "framer-motion";
import { StaffData, AttendanceData } from "../../schemas/IData";

interface AttendanceSectionProps {
  staffData: StaffData;
  attendance: Record<string, AttendanceData>;
  startDate: string;
  endDate: string;
  handleStartDateChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleEndDateChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  legendItems: string[];
}

const AttendanceSection: React.FC<AttendanceSectionProps> = ({
  staffData,
  attendance,
  startDate,
  endDate,
  handleStartDateChange,
  handleEndDateChange,
  legendItems,
}) => {
  return (
    <div className="px-8 pb-8 border-t border-gray-200 dark:border-gray-700">
      <div className="flex flex-col lg:flex-row items-center justify-between mb-6 gap-6">
        <div className="w-full max-w-md">
          <DateForm
            startDate={startDate}
            endDate={endDate}
            handleStartDateChange={handleStartDateChange}
            handleEndDateChange={handleEndDateChange}
            error=""
          />
        </div>
        <div className="flex flex-col items-center lg:items-end">
          <span className="inline-flex items-center text-lg text-gray-600 dark:text-gray-400">
            <FiInfo className="mr-2" />
            {formatDateRu(startDate)} - {formatDateRu(endDate)}
          </span>
          <span className="mt-1 text-xl font-semibold text-gray-800 dark:text-gray-100">
            Найдено {Object.keys(staffData.attendance).length}{" "}
            {declensionDays(Object.keys(staffData.attendance).length)}
          </span>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 mb-6">
        {legendItems.map((item, index) => {
          let colorClass = "";
          if (item === "Выходной день") {
            colorClass = "bg-amber-400 dark:bg-amber-500";
          } else if (item.includes("Работа в выходной")) {
            colorClass = "bg-green-400 dark:bg-green-500";
          } else if (item.includes("Удаленная работа")) {
            colorClass = "bg-sky-400 dark:bg-sky-500";
          } else if (item.includes("Одобрено")) {
            colorClass = "bg-violet-400 dark:bg-violet-500";
          } else if (item.includes("Не одобрено")) {
            colorClass = "bg-rose-400 dark:bg-rose-500";
          } else if (item === "Нет данных") {
            colorClass = "bg-red-400 dark:bg-red-500";
          } else {
            colorClass = "bg-gray-400 dark:bg-gray-500";
          }
          return (
            <motion.div
              key={index}
              className={`flex items-center space-x-2 px-4 py-1 rounded-full text-white text-sm ${colorClass}`}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.05, duration: 0.3 }}
            >
              <div className="w-2 h-2 rounded-full bg-white"></div>
              <span>{item}</span>
            </motion.div>
          );
        })}
      </div>
      <AttendanceTable attendance={attendance} />
    </div>
  );
};

export default AttendanceSection;
