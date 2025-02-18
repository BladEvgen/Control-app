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
    <div className="w-full sm:w-40">
      <label
        htmlFor={id}
        className="block mb-1 font-medium text-gray-200 dark:text-gray-400"
      >
        {label}
      </label>
      <input
        type="date"
        id={id}
        value={value}
        onChange={onChange}
        max={max}
        className="border border-gray-300 px-3 py-2 rounded-md w-full focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:text-white dark:border-gray-600"
      />
    </div>
  );
};

export default DateInput;
