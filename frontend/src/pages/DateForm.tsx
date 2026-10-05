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
    <div className="ws-date-range">
      <DateInput
        label="С"
        id={`${idPrefix}-startDate`}
        value={startDate}
        onChange={handleStartDateChange}
        max={maxDate}
      />
      <DateInput
        label="По"
        id={`${idPrefix}-endDate`}
        value={endDate}
        onChange={handleEndDateChange}
        max={maxDate}
      />
      {error ? <p className="ws-field-error">{error}</p> : null}
    </div>
  );
};

export default DateForm;
