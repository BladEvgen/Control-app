import React from "react";
import DateForm from "../DateForm";
import AttendanceTable from "../AttendanceTable";
import {
  formatDateRu,
  declensionDays,
  formatDateFromKeyRu,
} from "../../utils/utils";
import { FiInfo } from "react-icons/fi";
import { motion } from "framer-motion";
import {
  StaffData,
  AttendanceData,
  LessonAttendanceDayAudit,
} from "../../schemas/IData";
import {
  legendToneClass,
  type StaffAttendanceLegendChip,
} from "../../utils/attendanceDayPresentation";
import LessonAttendanceDayPanel from "./LessonAttendanceDayPanel";

interface AttendanceSectionProps {
  staffData: StaffData;
  attendance: Record<string, AttendanceData>;
  lessonAttendanceAudit: Record<string, LessonAttendanceDayAudit>;
  startDate: string;
  endDate: string;
  handleStartDateChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleEndDateChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  attendanceLegendChips: StaffAttendanceLegendChip[];
}

const AttendanceSection: React.FC<AttendanceSectionProps> = ({
  staffData,
  attendance,
  lessonAttendanceAudit,
  startDate,
  endDate,
  handleStartDateChange,
  handleEndDateChange,
  attendanceLegendChips,
}) => {
  const auditOnlyDates = Object.keys(lessonAttendanceAudit).filter(
    (dk) => !attendance[dk],
  );
  return (
    <div className="border-t border-gray-200 bg-gray-50/40 px-4 pb-6 dark:border-gray-800 dark:bg-black/15 sm:px-6 sm:pb-8 lg:px-8">
      <div className="flex flex-col lg:flex-row items-center justify-between mb-4 sm:mb-6 gap-4 sm:gap-6">
        <div className="w-full max-w-md">
          <DateForm
            startDate={startDate}
            endDate={endDate}
            handleStartDateChange={handleStartDateChange}
            handleEndDateChange={handleEndDateChange}
            error=""
          />
        </div>
        <div className="flex flex-col items-center lg:items-end w-full lg:w-auto">
          <span className="inline-flex items-center text-sm sm:text-lg text-gray-600 dark:text-gray-400">
            <FiInfo className="mr-2" />
            {formatDateRu(startDate)} - {formatDateRu(endDate)}
          </span>
          <span className="mt-1 text-lg sm:text-xl font-semibold text-gray-800 dark:text-gray-100">
            Найдено {Object.keys(staffData.attendance).length}{" "}
            {declensionDays(Object.keys(staffData.attendance).length)}
          </span>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 mb-6">
        {attendanceLegendChips.map((chip, index) => {
          const colorClass = legendToneClass(chip.tone);
          return (
            <motion.div
              key={chip.id}
              className={`flex items-center space-x-2 px-4 py-1 rounded-full text-white text-sm ${colorClass}`}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.05, duration: 0.3 }}
            >
              <div className="w-2 h-2 rounded-full bg-white"></div>
              <span>{chip.label}</span>
            </motion.div>
          );
        })}
      </div>
      <AttendanceTable attendance={attendance} />
      {auditOnlyDates.length > 0 ? (
        <div className="mt-6 border-t border-gray-200 pt-4 dark:border-gray-800">
          <h3 className="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">
            Журнал без строки в таблице
          </h3>
          <div className="grid gap-3 md:grid-cols-2">
            {auditOnlyDates.map((dk) => (
              <div key={dk}>
                <div className="mb-1 text-sm font-medium text-slate-800 dark:text-slate-100">
                  {formatDateFromKeyRu(dk)}
                </div>
                <LessonAttendanceDayPanel day={lessonAttendanceAudit[dk]} />
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default AttendanceSection;
