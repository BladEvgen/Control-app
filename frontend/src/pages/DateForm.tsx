import React from "react";
import DateInput from "../components/DateInput";

interface DateFormProps {
  startDate: string;
  endDate: string;
  handleStartDateChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleEndDateChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  error?: string;
  maxDate?: string;
  idPrefix?: string;
}

const DateForm: React.FC<DateFormProps> = ({
  startDate,
  endDate,
  handleStartDateChange,
  handleEndDateChange,
  error,
  maxDate,
  idPrefix = "attendance",
}) => {
  return (
    <div className="min-w-0">
      <div className="flex flex-col gap-4 lg:flex-row lg:gap-4">
        <div className="date-field-slot">
          <DateInput
            label="Начальная дата"
            id={`${idPrefix}-startDate`}
            value={startDate}
            onChange={handleStartDateChange}
            max={maxDate}
          />
        </div>
        <div className="date-field-slot">
          <DateInput
            label="Конечная дата"
            id={`${idPrefix}-endDate`}
            value={endDate}
            onChange={handleEndDateChange}
            max={maxDate}
          />
        </div>
      </div>
      {error ? (
        <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>
      ) : null}
    </div>
  );
};

export default DateForm;
