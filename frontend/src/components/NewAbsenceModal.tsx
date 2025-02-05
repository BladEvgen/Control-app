import React, { useState } from "react";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { motion, Variants } from "framer-motion";
import { FaTimes } from "react-icons/fa";
import { log } from "../api";
import { useDropzone, FileRejection } from "react-dropzone";

interface NewAbsenceModalProps {
  staffPin: string;
  onClose: () => void;
  onSuccess: () => void;
}

const ABSENT_REASON_CHOICES: { key: string; label: string }[] = [
  { key: "sick_leave", label: "Болезнь" },
  { key: "business_trip", label: "Командировка" },
  { key: "other", label: "Другая причина" },
];

const modalVariants: Variants = {
  initial: {
    opacity: 0,
    y: 100,
    scale: 0.95,
  },
  animate: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: "spring", stiffness: 120, damping: 20 },
  },
  exit: {
    opacity: 0,
    y: -50,
    scale: 0.95,
    transition: { duration: 0.3, ease: "easeInOut" },
  },
};

const NewAbsenceModal: React.FC<NewAbsenceModalProps> = ({
  staffPin,
  onClose,
  onSuccess,
}) => {
  const [reason, setReason] = useState<string>("sick_leave");
  const [startDate, setStartDate] = useState<string>(
    new Date().toISOString().split("T")[0]
  );
  const [endDate, setEndDate] = useState<string>(
    new Date().toISOString().split("T")[0]
  );
  const [approved, setApproved] = useState<boolean>(false);
  const [documentFile, setDocumentFile] = useState<File | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>("");

  const onDrop = (acceptedFiles: File[], fileRejections: FileRejection[]) => {
    if (fileRejections.length > 0) {
      setErrorMessage(
        "Неверный формат файла. Допустимые форматы: pdf, jpg, jpeg, png."
      );
      return;
    }
    if (acceptedFiles.length > 0) {
      const file = acceptedFiles[0];
      log.info("Выбран файл через drag & drop", file.name);
      setDocumentFile(file);
      setErrorMessage("");
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: false,
    accept: {
      "application/pdf": [".pdf"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/png": [".png"],
    },
  });

  const { onAnimationStart, ...dropzoneRootProps } = getRootProps();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    log.info("Отправка формы создания отсутствия", {
      staffPin,
      reason,
      startDate,
      endDate,
      approved,
    });
    const formData = new FormData();
    formData.append("staff", staffPin);
    formData.append("reason", reason);
    formData.append("start_date", startDate);
    formData.append("end_date", endDate);
    formData.append("approved", approved.toString());
    if (documentFile) {
      formData.append("document", documentFile);
      log.info("Прикреплён файл", documentFile.name);
    } else {
      log.warn("Файл не прикреплён");
    }
    try {
      await axiosInstance.post(`${apiUrl}/api/absent_staff/`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      log.info("Запись отсутствия создана успешно");
      onSuccess();
      onClose();
    } catch (error) {
      log.error("Ошибка при создании записи отсутствия", error);
      setErrorMessage("Ошибка при создании записи отсутствия");
    }
  };

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50 z-50 overflow-y-auto">
      <motion.div
        className="bg-white dark:bg-gray-800 p-8 rounded-xl shadow-2xl w-full max-w-md relative transition-all"
        variants={modalVariants}
        initial="initial"
        animate="animate"
        exit="exit"
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100 transition-colors"
        >
          <FaTimes size={22} />
        </button>
        <h2 className="text-2xl font-semibold mb-6 text-gray-800 dark:text-gray-100 text-center">
          Добавить отсутствие
        </h2>
        {errorMessage && (
          <motion.p
            className="text-red-500 mb-4 text-center font-medium"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          >
            {errorMessage}
          </motion.p>
        )}
        <form onSubmit={handleSubmit}>
          {/* Поле "Причина отсутствия" */}
          <div className="mb-5">
            <label className="block text-gray-700 dark:text-gray-300 mb-2">
              Причина отсутствия
            </label>
            <motion.select
              value={reason}
              onChange={(e) => {
                log.info("Выбрана причина", e.target.value);
                setReason(e.target.value);
              }}
              whileHover={{ scale: 1.02 }}
              whileFocus={{ scale: 1.02 }}
              className="w-full border border-gray-300 dark:border-gray-600 rounded-lg p-3 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-400 transition-all"
            >
              {ABSENT_REASON_CHOICES.map((choice) => (
                <option key={choice.key} value={choice.key}>
                  {choice.label}
                </option>
              ))}
            </motion.select>
          </div>
          {/* Начальная дата */}
          <div className="mb-5">
            <label className="block text-gray-700 dark:text-gray-300 mb-2">
              Начальная дата
            </label>
            <motion.input
              type="date"
              value={startDate}
              onChange={(e) => {
                log.info("Начальная дата изменена", e.target.value);
                setStartDate(e.target.value);
              }}
              whileHover={{ scale: 1.02 }}
              whileFocus={{ scale: 1.02 }}
              className="w-full border border-gray-300 dark:border-gray-600 rounded-lg p-3 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-400 transition-all"
            />
          </div>
          {/* Конечная дата */}
          <div className="mb-5">
            <label className="block text-gray-700 dark:text-gray-300 mb-2">
              Конечная дата
            </label>
            <motion.input
              type="date"
              value={endDate}
              onChange={(e) => {
                log.info("Конечная дата изменена", e.target.value);
                setEndDate(e.target.value);
              }}
              whileHover={{ scale: 1.02 }}
              whileFocus={{ scale: 1.02 }}
              className="w-full border border-gray-300 dark:border-gray-600 rounded-lg p-3 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-400 transition-all"
            />
          </div>
          {/* Checkbox "Утверждено" */}
          <div className="mb-5 flex items-center">
            <motion.label
              whileHover={{ scale: 1.05 }}
              className="relative inline-flex items-center cursor-pointer"
            >
              <input
                type="checkbox"
                checked={approved}
                onChange={(e) => {
                  log.info("Изменено состояние 'утверждено'", e.target.checked);
                  setApproved(e.target.checked);
                }}
                className="sr-only peer"
              />
              <div
                className="w-11 h-6 bg-gray-300 dark:bg-gray-600 rounded-full peer 
                peer-checked:after:translate-x-full peer-checked:after:border-white 
                after:content-[''] after:absolute after:top-[2px] after:left-[2px]
                after:bg-white after:border-gray-300 after:border after:rounded-full 
                after:h-5 after:w-5 after:transition-all dark:border-gray-500 peer-checked:bg-blue-500"
              />
            </motion.label>
            <span className="ml-3 text-gray-700 dark:text-gray-300 select-none">
              Утверждено
            </span>
          </div>
          {/* Загрузка файла с drag & drop */}
          <div className="mb-5">
            <label className="block text-gray-700 dark:text-gray-300 mb-2">
              Прикрепить документ
            </label>
            <div
              {...dropzoneRootProps}
              className={`cursor-pointer flex items-center justify-center border-2 border-dashed rounded-lg p-6 transition-all hover:scale-[1.03] active:scale-[0.98] ${
                isDragActive
                  ? "bg-blue-50 border-blue-500"
                  : "bg-white dark:bg-gray-700 border-gray-300"
              }`}
            >
              <input {...getInputProps()} />
              {documentFile ? (
                <p className="text-gray-800 dark:text-gray-200 truncate">
                  {documentFile.name}
                </p>
              ) : (
                <p className="text-gray-500 dark:text-gray-400">
                  {isDragActive
                    ? "Отпустите файл здесь"
                    : "Нажмите или перетащите файл сюда"}
                </p>
              )}
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
              Допустимые форматы: pdf, jpg, jpeg, png.
            </p>
          </div>
          <motion.button
            type="submit"
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.98 }}
            className="w-full bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 dark:from-blue-600 dark:to-blue-700 dark:hover:from-blue-700 dark:hover:to-blue-800 text-white py-3 rounded-lg font-semibold transition-all shadow-md hover:shadow-xl"
          >
            Сохранить
          </motion.button>
        </form>
      </motion.div>
    </div>
  );
};

export default NewAbsenceModal;
