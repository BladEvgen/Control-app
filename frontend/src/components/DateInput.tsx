import React from "react";
import { FaCalendarAlt } from "react-icons/fa";
import { motion } from "framer-motion";

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
  const formattedValue = value || "";

  return (
    <motion.div
      className="relative w-full"
      whileHover={{ scale: 1.01 }}
      transition={{ duration: 0.2 }}
    >
      <label
        htmlFor={id}
        className="block mb-2 font-medium text-sm text-gray-600 dark:text-gray-300"
      >
        {label}
      </label>
      <div className="relative">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <FaCalendarAlt className="h-5 w-5 text-gray-400 dark:text-gray-500" />
        </div>
        <input
          type="date"
          id={id}
          value={formattedValue}
          onChange={onChange}
          max={max}
          className="bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 pl-10 pr-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg shadow-sm w-full focus:outline-none focus:ring-2 focus:ring-primary-500 dark:focus:ring-primary-600 focus:border-transparent transition-all duration-200"
          style={{ width: "100%", minWidth: "220px" }}
        />
      </div>
    </motion.div>
  );
};

export default DateInput;
