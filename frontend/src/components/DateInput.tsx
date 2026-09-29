import React from "react";

interface DateInputProps {
  label: string;
  id: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  max?: string;
}

const DateInput: React.FC<DateInputProps> = ({
  label,
  id,
  value,
  onChange,
  max,
}) => {
  return (
    <div className="relative">
      <label
        htmlFor={id}
        className="mb-2 block text-sm font-medium text-gray-800 dark:text-gray-200"
      >
        {label}
      </label>
      <input
        type="date"
        id={id}
        value={value || ""}
        onChange={onChange}
        max={max}
        className="date-input-control w-full rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-gray-800 shadow-sm transition-all duration-200 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/35 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100 dark:focus:border-primary-500 dark:focus:ring-primary-500/40"
      />
    </div>
  );
};

export default DateInput;
