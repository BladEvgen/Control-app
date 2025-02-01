import React from "react";

interface DateFormProps {
  startDate: string;
  endDate: string;
  handleStartDateChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleEndDateChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  error?: string;
}

const DateForm: React.FC<DateFormProps> = ({
  startDate,
  endDate,
  handleStartDateChange,
  handleEndDateChange,
  error,
}) => {
  return (
    <div className="w-full">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label
            htmlFor="startDate"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            Начальная дата
          </label>
          <input
            id="startDate"
            type="date"
            value={startDate}
            onChange={handleStartDateChange}
            className="mt-1 block w-full rounded-md border border-gray-200 shadow-sm focus:border-blue-500 focus:ring-blue-500 bg-white dark:bg-transparent dark:text-gray-100"
          />
        </div>
        <div>
          <label
            htmlFor="endDate"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            Конечная дата
          </label>
          <input
            id="endDate"
            type="date"
            value={endDate}
            onChange={handleEndDateChange}
            className="mt-1 block w-full rounded-md border border-gray-200 shadow-sm focus:border-blue-500 focus:ring-blue-500 bg-white dark:bg-transparent dark:text-gray-100"
          />
        </div>
      </div>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
};

export default DateForm;
