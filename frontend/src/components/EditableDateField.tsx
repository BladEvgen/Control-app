import React, { useState } from "react";
import { motion } from "framer-motion";
import useWindowSize from "../hooks/useWindowSize";

interface EditableDateFieldProps {
  /** Значение даты в формате yyyy-mm-dd */
  value: string;
  /** Обработчик изменения даты */
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  /** Текст, который будет выводиться перед датой (необязательно) */
  label?: string;
  /** Дополнительный класс для контейнера */
  containerClassName?: string;
  /** Дополнительный класс для метки */
  labelClassName?: string;
  /** Дополнительный класс для поля ввода (в режиме редактирования) */
  inputClassName?: string;
  /** Дополнительный класс для отображаемого текста (в режиме просмотра) */
  displayClassName?: string;
}

const EditableDateField: React.FC<EditableDateFieldProps> = ({
  value,
  onChange,
  label,
  containerClassName,
  labelClassName,
  inputClassName,
  displayClassName,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const { width } = useWindowSize();

  const isSmallScreen = width < 1024;

  const defaultContainerClass = "flex flex-col items-center";
  const defaultLabelClass = isSmallScreen
    ? "text-center mb-2 text-white text-sm"
    : "text-center mb-2 text-white text-base";
  const defaultInputClass = isSmallScreen
    ? "w-full max-w-xs p-2 border border-gray-300 rounded shadow-md text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
    : "w-full max-w-xs p-3 border border-gray-300 rounded shadow-md text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-base";
  const defaultDisplayClass = isSmallScreen
    ? "w-full max-w-xs cursor-pointer text-center hover:underline transition-all duration-200 text-white text-sm"
    : "w-full max-w-xs cursor-pointer text-center hover:underline transition-all duration-200 text-white text-base";

  const formatDateForDisplay = (dateStr: string): string => {
    if (!dateStr) return "";
    const parts = dateStr.split("-");
    if (parts.length !== 3) return dateStr;
    const [year, month, day] = parts;
    return `${day}.${month}.${year}`;
  };

  return (
    <div className={containerClassName || defaultContainerClass}>
      {label && (
        <label className={labelClassName || defaultLabelClass}>{label}</label>
      )}
      {isEditing ? (
        <motion.input
          type="date"
          value={value}
          onChange={onChange}
          onBlur={() => setIsEditing(false)}
          autoFocus
          className={inputClassName || defaultInputClass}
          whileFocus={{
            scale: 1.05,
            boxShadow: "0 0 8px rgba(0, 123, 255, 0.6)",
          }}
          transition={{ type: "spring", stiffness: 300 }}
        />
      ) : (
        <motion.span
          onClick={() => setIsEditing(true)}
          className={displayClassName || defaultDisplayClass}
        >
          {formatDateForDisplay(value)}
        </motion.span>
      )}
    </div>
  );
};

export default EditableDateField;
