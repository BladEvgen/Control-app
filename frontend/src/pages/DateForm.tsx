import React from "react";

interface DateFormProps {
  startDate: string;
  endDate: string;
  handleStartDateChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleEndDateChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  error: string;
}

const DateForm: React.FC<DateFormProps> = ({
  startDate,
  endDate,
  handleStartDateChange,
  handleEndDateChange,
  error,
}) => {
  return (
    <div className="mb-4 flex flex-col sm:flex-row sm:space-x-4 justify-center sm:justify-between items-center sm:items-end">
      <div className="mb-2 sm:mb-0 w-full sm:w-auto">
        <label
          htmlFor="startDate"
          className="block text-sm font-medium text-gray-700 dark:text-gray-400 mb-1"
        >
          Дата начала:
        </label>
        <input
          type="date"
          id="startDate"
          value={startDate}
          onChange={handleStartDateChange}
          className="rounded-lg border-gray-300 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50 w-full sm:w-auto transition-colors duration-300 dark:bg-gray-800 dark:text-white dark:border-gray-600 text-center"
          placeholder="Дата начала"
        />
      </div>
      {startDate && (
        <div className="mt-2 sm:mt-0 w-full sm:w-auto">
          <label
            htmlFor="endDate"
            className="block text-sm font-medium text-gray-700 dark:text-gray-400 mb-1"
          >
            Дата окончания:
          </label>
          <input
            type="date"
            id="endDate"
            value={endDate}
            onChange={handleEndDateChange}
            className="rounded-lg border-gray-300 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50 w-full sm:w-auto transition-colors duration-300 dark:bg-gray-800 dark:text-white dark:border-gray-600 text-center"
            placeholder="Дата окончания"
          />
        </div>
      )}
      {error && <p className="text-red-600 dark:text-red-400 mt-2">{error}</p>}
    </div>
  );
};

export default DateForm;
