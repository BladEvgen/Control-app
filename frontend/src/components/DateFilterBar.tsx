import React from "react";
import DateInput from "./DateInput";
import ModernButton from "./ModernButton";
import { FaDownload, FaCalendarWeek } from "react-icons/fa";
import { motion } from "framer-motion";

interface DateFilterBarProps {
  startDate: string;
  endDate: string;
  onStartDateChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onEndDateChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onDownload: () => void;
  isDownloading: boolean;
  isDownloadDisabled: boolean;
  today: string;
}

const DateFilterBar: React.FC<DateFilterBarProps> = ({
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
  onDownload,
  isDownloading,
  isDownloadDisabled,
  today,
}) => {
  return (
    <motion.div
      className="card p-5 mb-6"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div className="flex flex-col md:flex-row items-start md:items-end gap-4">
        <div className="w-full">
          <div className="flex items-center mb-3">
            <FaCalendarWeek className="text-primary-600 dark:text-primary-400 mr-2" />
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
              Диапазон дат
            </h3>
          </div>
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="w-full sm:w-40 lg:w-60">
              <DateInput
                label="Дата начала"
                id="startDate"
                value={startDate}
                onChange={onStartDateChange}
                max={today}
              />
            </div>
            <div className="w-full sm:w-40 lg:w-60">
              <DateInput
                label="Дата окончания"
                id="endDate"
                value={endDate}
                onChange={onEndDateChange}
                max={today}
              />
            </div>
          </div>
        </div>

        <div className="w-full md:w-auto mt-4 md:mt-0 self-end">
          <ModernButton
            variant="download"
            icon={<FaDownload />}
            onClick={onDownload}
            disabled={isDownloadDisabled}
            loading={isDownloading}
            className="w-full md:w-auto py-2.5"
          >
            {isDownloading ? "Загрузка..." : "Загрузить"}
          </ModernButton>
        </div>
      </div>
    </motion.div>
  );
};

export default DateFilterBar;
