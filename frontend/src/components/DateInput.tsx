import React, { useCallback, useRef } from "react";
import { FaCalendarAlt } from "react-icons/fa";

interface DateInputProps {
  label: string;
  id: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  max?: string;
}

function openNativeDatePicker(input: HTMLInputElement | null) {
  if (!input) return;
  try {
    input.showPicker?.();
  } catch {
    input.focus();
    input.click();
  }
}

const DateInput: React.FC<DateInputProps> = ({
  label,
  id,
  value,
  onChange,
  max,
}) => {
  const formattedValue = value || "";
  const inputRef = useRef<HTMLInputElement>(null);

  const onOpenPicker = useCallback(() => {
    openNativeDatePicker(inputRef.current);
  }, []);

  return (
    <div className="relative">
      <label
        htmlFor={id}
        className="mb-2 block text-sm font-medium text-gray-800 dark:text-gray-200"
      >
        {label}
      </label>
      <div className="relative">
        <button
          type="button"
          className="absolute inset-y-0 left-0 z-[1] flex items-center rounded-l-lg pl-3 pr-2 text-gray-600 transition-colors hover:text-primary-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 dark:text-gray-200 dark:hover:text-primary-300 dark:focus-visible:ring-primary-400/45"
          onClick={onOpenPicker}
          aria-label={`Открыть календарь: ${label}`}
        >
          <FaCalendarAlt className="h-5 w-5 shrink-0" aria-hidden />
        </button>
        <input
          ref={inputRef}
          type="date"
          id={id}
          value={formattedValue}
          onChange={onChange}
          max={max}
          className="date-input-control w-full rounded-lg border border-gray-300 bg-white py-2.5 pl-10 pr-3 text-gray-800 shadow-sm transition-all duration-200 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/35 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100 dark:focus:border-primary-500 dark:focus:ring-primary-500/40"
        />
      </div>
    </div>
  );
};

export default DateInput;
