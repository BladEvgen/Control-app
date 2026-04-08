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
            className="block text-sm font-medium text-gray-800 dark:text-gray-200"
          >
            Начальная дата
          </label>
          <input
            id="startDate"
            type="date"
            value={startDate}
            onChange={handleStartDateChange}
            className="mt-1 block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500/30 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100 dark:focus:border-primary-500"
          />
        </div>
        <div>
          <label
            htmlFor="endDate"
            className="block text-sm font-medium text-gray-800 dark:text-gray-200"
          >
            Конечная дата
          </label>
          <input
            id="endDate"
            type="date"
            value={endDate}
            onChange={handleEndDateChange}
            className="mt-1 block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500/30 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100 dark:focus:border-primary-500"
          />
        </div>
      </div>
      {error && (
        <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>
      )}
    </div>
  );
};

export default DateForm;
