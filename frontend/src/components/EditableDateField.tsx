import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import useWindowSize from "../hooks/useWindowSize";
import { FaCheck } from "react-icons/fa";

interface EditableDateFieldProps {
  /** Значение даты в формате yyyy-mm-dd */
  value: string;
  /** Обработчик изменения даты (вызывается только при завершении редактирования) */
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
  const [draftValue, setDraftValue] = useState(value);
  const { width } = useWindowSize();

  const isSmallScreen = width < 1024;

  const defaultContainerClass = "flex flex-col items-center";
  const defaultLabelClass = isSmallScreen
    ? "text-center mb-2 text-white text-sm"
    : "text-center mb-2 text-white text-base";
  const defaultInputClass = isSmallScreen
    ? "w-full max-w-xs p-2 border border-gray-300 rounded shadow-sm text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
    : "w-full max-w-xs p-3 border border-gray-300 rounded shadow-sm text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-base";
  const defaultDisplayClass = isSmallScreen
    ? "w-full max-w-xs cursor-pointer text-center hover:underline transition-all duration-200 text-gray-700 text-sm"
    : "w-full max-w-xs cursor-pointer text-center hover:underline transition-all duration-200 text-gray-700 text-base";

  const hintTextClass = isSmallScreen ? "text-xs" : "text-sm";

  const formatDateForDisplay = (dateStr: string): string => {
    if (!dateStr) return "";
    const parts = dateStr.split("-");
    if (parts.length !== 3) return dateStr;
    const [year, month, day] = parts;
    return `${day}.${month}.${year}`;
  };

  useEffect(() => {
    if (!isEditing) {
      setDraftValue(value);
    }
  }, [value, isEditing]);

  const handleFinishEditing = () => {
    setIsEditing(false);
    const syntheticEvent = {
      target: { value: draftValue },
    } as React.ChangeEvent<HTMLInputElement>;
    onChange(syntheticEvent);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleFinishEditing();
    }
  };

  return (
    <div className={containerClassName || defaultContainerClass}>
      {label && (
        <label className={labelClassName || defaultLabelClass}>{label}</label>
      )}
      {isEditing ? (
        <div className="flex items-center space-x-2">
          <motion.input
            type="date"
            value={draftValue}
            onChange={(e) => setDraftValue(e.target.value)}
            onBlur={handleFinishEditing}
            onKeyDown={handleKeyDown}
            autoFocus
            max={new Date().toISOString().split("T")[0]}
            className={inputClassName || defaultInputClass}
            whileFocus={{
              scale: 1.02,
              boxShadow: "0 0 4px rgba(0, 123, 255, 0.5)",
            }}
            transition={{ type: "spring", stiffness: 300 }}
          />
          <motion.button
            onClick={handleFinishEditing}
            className="p-1 text-green-600 hover:text-green-800 focus:outline-none"
            whileTap={{ scale: 0.95 }}
            title="Подтвердить дату"
          >
            <FaCheck className="w-4 h-4" />
          </motion.button>
        </div>
      ) : (
        <motion.span
          onClick={() => setIsEditing(true)}
          className={displayClassName || defaultDisplayClass}
        >
          {formatDateForDisplay(value)}
        </motion.span>
      )}
      {isEditing && (
        <motion.p
          className={`mt-1 text-center text-gray-600 ${hintTextClass}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          Нажмите Enter или на иконку для подтверждения
        </motion.p>
      )}
    </div>
  );
};

export default EditableDateField;
