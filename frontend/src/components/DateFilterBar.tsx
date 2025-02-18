import React from "react";
import DateInput from "./DateInput";
import ModernButton from "./ModernButton";
import { FaDownload } from "react-icons/fa";

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
    <div className="mb-4 px-2 flex flex-col space-y-4 md:space-y-0 md:flex-row md:items-end md:space-x-4">
      <div className="w-full md:w-40">
        <DateInput
          label="Дата начала:"
          id="startDate"
          value={startDate}
          onChange={onStartDateChange}
          max={today}
        />
      </div>
      <div className="w-full md:w-40">
        <DateInput
          label="Дата конца:"
          id="endDate"
          value={endDate}
          onChange={onEndDateChange}
          max={today}
        />
      </div>
      <div className="w-full md:w-auto">
        <ModernButton
          variant="download"
          icon={<FaDownload />}
          onClick={onDownload}
          disabled={isDownloadDisabled}
          loading={isDownloading}
          className="w-full md:w-auto"
        >
          {isDownloading ? "Загрузка..." : "Скачать"}
        </ModernButton>
      </div>
    </div>
  );
};

export default DateFilterBar;
