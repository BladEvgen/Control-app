import React, { useEffect, useState } from "react";
import DateInput from "./DateInput";
import ModernButton from "./ModernButton";
import { FaDownload, FaCalendarWeek } from "react-icons/fa";
import { motion } from "framer-motion";
import { subscribeAttendanceExcelDownloads } from "../utils/attendanceExcelDownloadHub";

interface DateFilterBarProps {
  startDate: string;
  endDate: string;
  onStartDateChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onEndDateChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onDownload: () => void;
  isDownloadDisabled: boolean;
  excelHoldKey?: string | null;
  today: string;
  idPrefix?: string;
}

const DateFilterBar: React.FC<DateFilterBarProps> = ({
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
  onDownload,
  isDownloadDisabled,
  excelHoldKey,
  today,
  idPrefix = "filter",
}) => {
  const [holdCounts, setHoldCounts] = useState<Map<string, number>>(
    () => new Map(),
  );

  useEffect(
    () =>
      subscribeAttendanceExcelDownloads(({ holdCounts: next }) =>
        setHoldCounts(next),
      ),
    [],
  );

  const heldHere =
    excelHoldKey != null &&
    excelHoldKey !== "" &&
    (holdCounts.get(excelHoldKey) ?? 0) > 0;
  const nHere = excelHoldKey != null ? (holdCounts.get(excelHoldKey) ?? 0) : 0;

  const downloadLabel = heldHere
    ? nHere > 1
      ? `Загрузка (${nHere})…`
      : "Загрузка…"
    : "Загрузить";

  const startId = `${idPrefix}-startDate`;
  const endId = `${idPrefix}-endDate`;

  return (
    <motion.div
      className="card mb-6 overflow-x-hidden p-5"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:gap-6">
        <div className="min-w-0 flex-1">
          <div className="mb-3 flex items-center">
            <FaCalendarWeek className="mr-2 shrink-0 text-primary-600 dark:text-primary-400" />
            <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">
              Диапазон дат
            </h3>
          </div>
          <div className="flex flex-col gap-4 lg:flex-row lg:gap-4">
            <div className="date-field-slot">
              <DateInput
                label="Дата начала"
                id={startId}
                value={startDate}
                onChange={onStartDateChange}
                max={today}
              />
            </div>
            <div className="date-field-slot">
              <DateInput
                label="Дата окончания"
                id={endId}
                value={endDate}
                onChange={onEndDateChange}
                max={today}
              />
            </div>
          </div>
        </div>

        <div className="date-filter-action shrink-0">
          <ModernButton
            variant="download"
            icon={<FaDownload />}
            onClick={onDownload}
            disabled={isDownloadDisabled || heldHere}
            loading={heldHere}
            className="w-full py-2.5 md:w-auto"
          >
            {downloadLabel}
          </ModernButton>
        </div>
      </div>
    </motion.div>
  );
};

export default DateFilterBar;
