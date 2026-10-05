import React from "react";
import DateForm from "../DateForm";
import AttendanceTable from "../AttendanceTable";
import {
  formatDateRu,
  declensionDays,
  formatDateFromKeyRu,
} from "../../utils/utils";
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
    <div className="staff-attendance">
      <div className="staff-attendance-head">
        <DateForm
          startDate={startDate}
          endDate={endDate}
          handleStartDateChange={handleStartDateChange}
          handleEndDateChange={handleEndDateChange}
          error=""
          maxDate={today}
          idPrefix="staff-attendance"
        />
        <p className="staff-attendance-summary">
          <strong>
            {dayCount} {declensionDays(dayCount)}
          </strong>
          <span>
            {formatDateRu(startDate)} — {formatDateRu(endDate)}
          </span>
        </p>
      </div>

      <div className="staff-legend">
        {attendanceLegendChips.map((chip, index) => {
          const colorClass = legendToneClass(chip.tone);
          return (
            <motion.div
              key={chip.id}
              className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium text-white ${colorClass}`}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.05, duration: 0.3 }}
            >
              <div className="h-1.5 w-1.5 shrink-0 rounded-full bg-white" />
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
