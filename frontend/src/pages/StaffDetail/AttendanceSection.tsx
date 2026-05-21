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
  today?: string;
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
  today,
}) => {
  const auditOnlyDates = Object.keys(lessonAttendanceAudit).filter(
    (dk) => !attendance[dk],
  );
  const dayCount = Object.keys(staffData.attendance).length;

  return (
    <div className="border-t border-gray-200 bg-gray-50/40 px-4 pb-6 dark:border-gray-800 dark:bg-black/15 sm:px-6 sm:pb-8 lg:px-8">
      <div className="mb-4 flex flex-col gap-5 sm:mb-6 lg:flex-row lg:items-end lg:justify-between lg:gap-8">
        <div className="min-w-0 w-full lg:flex-1">
          <DateForm
            startDate={startDate}
            endDate={endDate}
            handleStartDateChange={handleStartDateChange}
            handleEndDateChange={handleEndDateChange}
            error=""
            maxDate={today}
            idPrefix="staff-attendance"
          />
        </div>
        <div className="w-full shrink-0 border-t border-gray-200/80 pt-4 dark:border-gray-700/80 max-lg:max-w-[17.5rem] lg:w-auto lg:max-w-xs lg:border-t-0 lg:pt-0 lg:text-right">
          <span className="inline-flex items-center text-sm text-gray-600 dark:text-gray-400 sm:text-base">
            <FiInfo className="mr-2 shrink-0" aria-hidden />
            <span className="break-words">
              {formatDateRu(startDate)} — {formatDateRu(endDate)}
            </span>
          </span>
          <p className="mt-2 text-lg font-semibold text-gray-800 dark:text-gray-100 sm:text-xl">
            Найдено {dayCount} {declensionDays(dayCount)}
          </p>
        </div>
      </div>

      <div className="mb-6 flex flex-wrap gap-2">
        {attendanceLegendChips.map((chip, index) => {
          const colorClass = legendToneClass(chip.tone);
          return (
            <motion.div
              key={chip.id}
              className={`flex items-center space-x-2 rounded-full px-3 py-1.5 text-sm text-white sm:px-4 ${colorClass}`}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.05, duration: 0.3 }}
            >
              <div className="h-2 w-2 shrink-0 rounded-full bg-white" />
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
