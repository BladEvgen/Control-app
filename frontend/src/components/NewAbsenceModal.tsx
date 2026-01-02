import React, { useState, useMemo } from "react";
import ReactDOM from "react-dom";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { motion, Variants } from "framer-motion";
import {
  FaTimes,
  FaCalendarAlt,
  FaFileUpload,
  FaCheckCircle,
  FaExclamationTriangle,
  FaFilePdf,
  FaFileImage,
  FaTrash,
} from "react-icons/fa";
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

  const getInitialDates = () => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    return {
      start: yesterday.toISOString().split("T")[0],
      end: today.toISOString().split("T")[0],
      max: today.toISOString().split("T")[0],
    };
  };

  const initialDates = getInitialDates();
  const [startDate, setStartDate] = useState<string>(initialDates.start);
  const [endDate, setEndDate] = useState<string>(initialDates.end);
  const [approved, setApproved] = useState<boolean>(false);
  const [documentFile, setDocumentFile] = useState<File | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const maxDate = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return today.toISOString().split("T")[0];
  }, []);

  const daysDifference = useMemo(() => {
    if (!startDate || !endDate) return 0;
    const start = new Date(startDate);
    const end = new Date(endDate);
    const diffTime = Math.abs(end.getTime() - start.getTime());
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)) + 1;
    return diffDays;
  }, [startDate, endDate]);

  const dateError = useMemo(() => {
    if (!startDate || !endDate) return null;

    const start = new Date(startDate + "T00:00:00");
    const end = new Date(endDate + "T00:00:00");
    const today = new Date(maxDate + "T00:00:00");

    if (start > today) {
      return "Начальная дата не может быть в будущем";
    }
    if (end > today) {
      return "Конечная дата не может быть в будущем";
    }

    if (end < start) {
      return "Конечная дата не может быть раньше начальной";
    }

    return null;
  }, [startDate, endDate, maxDate]);

  const onDrop = (acceptedFiles: File[], fileRejections: FileRejection[]) => {
    setErrorMessage("");

    if (fileRejections.length > 0) {
      const rejection = fileRejections[0];
      if (rejection.errors.some((e) => e.code === "file-too-large")) {
        setErrorMessage("Файл слишком большой. Максимальный размер: 10 МБ.");
      } else if (rejection.errors.some((e) => e.code === "file-invalid-type")) {
        setErrorMessage(
          "Неверный формат файла. Допустимые форматы: PDF, JPG, JPEG, PNG."
        );
      } else {
        setErrorMessage("Ошибка при загрузке файла. Попробуйте еще раз.");
      }
      return;
    }

    if (acceptedFiles.length > 0) {
      const file = acceptedFiles[0];
      log.info("Выбран файл", file.name);
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
    maxSize: 10 * 1024 * 1024,
    disabled: isSubmitting,
  });

  const dropzoneProps = getRootProps();
  const {
    onAnimationStart,
    onDrag,
    onDragEnd,
    onDragStart,
    ...dropzoneRootProps
  } = dropzoneProps;
  void onAnimationStart;
  void onDrag;
  void onDragEnd;
  void onDragStart;

  const getFileIcon = (fileName: string) => {
    const ext = fileName.split(".").pop()?.toLowerCase();
    if (ext === "pdf") {
      return <FaFilePdf className="h-5 w-5 text-red-500 dark:text-red-400" />;
    }
    if (["jpg", "jpeg", "png"].includes(ext || "")) {
      return (
        <FaFileImage className="h-5 w-5 text-blue-500 dark:text-blue-400" />
      );
    }
    return (
      <FaFileUpload className="h-5 w-5 text-gray-500 dark:text-gray-400" />
    );
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} Б`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} МБ`;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Проверка валидации дат
    if (dateError) {
      setErrorMessage(dateError);
      return;
    }

    setIsSubmitting(true);
    setErrorMessage("");

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
      await axiosInstance.post(`${apiUrl}/api/absent_staff/`, formData);
      log.info("Запись отсутствия создана успешно");
      onSuccess();
      onClose();
    } catch (error) {
      log.error("Ошибка при создании записи отсутствия", error);
      if (error && typeof error === "object" && "response" in error) {
        const axiosError = error as {
          response?: { status?: number; data?: unknown };
        };
        if (axiosError.response?.status === 403) {
          setErrorMessage("Доступ запрещен. Проверьте авторизацию.");
        } else if (axiosError.response?.status === 400) {
          const errorData = axiosError.response.data;
          if (errorData && typeof errorData === "object") {
            const errorMessage = Object.values(errorData).join(", ");
            setErrorMessage(`Ошибка валидации: ${errorMessage}`);
          } else {
            setErrorMessage("Ошибка при создании записи отсутствия");
          }
        } else {
          setErrorMessage("Ошибка при создании записи отсутствия");
        }
      } else {
        setErrorMessage("Ошибка при создании записи отсутствия");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleStartDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newStartDate = e.target.value;
    log.info("Начальная дата изменена", newStartDate);

    if (newStartDate > maxDate) {
      setErrorMessage("Начальная дата не может быть в будущем");
      return;
    }

    setStartDate(newStartDate);
    setErrorMessage("");

    if (endDate && newStartDate > endDate) {
      setEndDate(newStartDate);
      log.info("Конечная дата автоматически обновлена", newStartDate);
    }
  };

  const handleEndDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newEndDate = e.target.value;
    log.info("Конечная дата изменена", newEndDate);

    if (newEndDate > maxDate) {
      setErrorMessage("Конечная дата не может быть в будущем");
      return;
    }

    if (startDate && newEndDate < startDate) {
      setErrorMessage("Конечная дата не может быть раньше начальной");
      return;
    }

    setEndDate(newEndDate);
    setErrorMessage("");
  };

  return ReactDOM.createPortal(
    <>
      {/* Overlay loader при отправке */}
      {isSubmitting && (
        <motion.div
          className="fixed inset-0 bg-black bg-opacity-70 z-[1001] flex items-center justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div className="bg-white dark:bg-gray-800 rounded-xl p-8 shadow-2xl flex flex-col items-center gap-4">
            <motion.div
              className="w-12 h-12 border-4 border-primary-500 border-t-transparent rounded-full"
              animate={{ rotate: 360 }}
              transition={{ duration: 0.8, repeat: Infinity, ease: "linear" }}
            />
            <p className="text-lg font-medium text-gray-800 dark:text-gray-200">
              Сохранение отсутствия...
            </p>
          </div>
        </motion.div>
      )}
      <div className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50 z-[1000] p-2 sm:p-4">
        <motion.div
          className="card w-full max-w-lg max-h-[90vh] sm:max-h-[95vh] relative overflow-hidden flex flex-col"
          variants={modalVariants}
          initial="initial"
          animate="animate"
          exit="exit"
        >
          {/* Заголовок */}
          <div className="flex items-center justify-between p-3 sm:p-4 md:p-6 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
            <h2 className="text-lg sm:text-xl md:text-2xl font-semibold text-gray-800 dark:text-gray-100">
              Добавить отсутствие
            </h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
              disabled={isSubmitting}
            >
              <FaTimes size={20} />
            </button>
          </div>

          {/* Контент */}
          <div className="p-3 sm:p-4 md:p-6 overflow-y-auto flex-1">
            {errorMessage && (
              <motion.div
                className="mb-4 p-3 rounded-lg bg-danger-50 dark:bg-danger-900/20 border border-danger-200 dark:border-danger-800 flex items-start gap-2"
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <FaExclamationTriangle className="text-danger-500 dark:text-danger-400 mt-0.5 flex-shrink-0" />
                <p className="text-danger-700 dark:text-danger-400 text-sm font-medium">
                  {errorMessage}
                </p>
              </motion.div>
            )}

            {dateError && (
              <motion.div
                className="mb-4 p-3 rounded-lg bg-warning-50 dark:bg-warning-900/20 border border-warning-200 dark:border-warning-800 flex items-start gap-2"
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <FaExclamationTriangle className="text-warning-500 dark:text-warning-400 mt-0.5 flex-shrink-0" />
                <p className="text-warning-700 dark:text-warning-400 text-sm font-medium">
                  {dateError}
                </p>
              </motion.div>
            )}
            <form
              onSubmit={handleSubmit}
              className="space-y-3 sm:space-y-4 md:space-y-5"
            >
              {/* Поле "Причина отсутствия" */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Причина отсутствия
                </label>
                <div className="relative">
                  <motion.select
                    value={reason}
                    onChange={(e) => {
                      log.info("Выбрана причина", e.target.value);
                      setReason(e.target.value);
                    }}
                    whileHover={{ scale: 1.01 }}
                    whileFocus={{ scale: 1.01 }}
                    className="w-full border border-gray-300 dark:border-gray-600 rounded-lg pl-10 pr-4 py-2.5 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-primary-500 dark:focus:ring-primary-600 focus:border-transparent transition-all appearance-none"
                    disabled={isSubmitting}
                  >
                    {ABSENT_REASON_CHOICES.map((choice) => (
                      <option key={choice.key} value={choice.key}>
                        {choice.label}
                      </option>
                    ))}
                  </motion.select>
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <FaExclamationTriangle className="h-4 w-4 text-gray-400 dark:text-gray-500" />
                  </div>
                </div>
              </div>

              {/* Даты в одной строке */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Начальная дата */}
                <div>
                  <label
                    htmlFor="startDate"
                    className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2"
                  >
                    Начальная дата
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <FaCalendarAlt className="h-4 w-4 text-gray-400 dark:text-gray-500" />
                    </div>
                    <motion.input
                      type="date"
                      id="startDate"
                      value={startDate}
                      onChange={handleStartDateChange}
                      max={maxDate}
                      whileHover={{ scale: 1.01 }}
                      whileFocus={{ scale: 1.01 }}
                      className={`w-full border rounded-lg pl-10 pr-4 py-2.5 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-primary-500 dark:focus:ring-primary-600 focus:border-transparent transition-all ${
                        dateError
                          ? "border-danger-300 dark:border-danger-700"
                          : "border-gray-300 dark:border-gray-600"
                      }`}
                      disabled={isSubmitting}
                    />
                  </div>
                </div>

                {/* Конечная дата */}
                <div>
                  <label
                    htmlFor="endDate"
                    className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2"
                  >
                    Конечная дата
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <FaCalendarAlt className="h-4 w-4 text-gray-400 dark:text-gray-500" />
                    </div>
                    <motion.input
                      type="date"
                      id="endDate"
                      value={endDate}
                      onChange={handleEndDateChange}
                      min={startDate}
                      max={maxDate}
                      whileHover={{ scale: 1.01 }}
                      whileFocus={{ scale: 1.01 }}
                      className={`w-full border rounded-lg pl-10 pr-4 py-2.5 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-primary-500 dark:focus:ring-primary-600 focus:border-transparent transition-all ${
                        dateError
                          ? "border-danger-300 dark:border-danger-700"
                          : "border-gray-300 dark:border-gray-600"
                      }`}
                      disabled={isSubmitting}
                    />
                  </div>
                </div>
              </div>

              {/* Информация о количестве дней */}
              {!dateError && startDate && endDate && daysDifference > 0 && (
                <motion.div
                  className="p-3 rounded-lg bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800 flex items-center gap-2"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                >
                  <FaCheckCircle className="text-primary-500 dark:text-primary-400 flex-shrink-0" />
                  <p className="text-primary-700 dark:text-primary-400 text-sm">
                    Период отсутствия: <strong>{daysDifference}</strong>{" "}
                    {daysDifference === 1
                      ? "день"
                      : daysDifference < 5
                      ? "дня"
                      : "дней"}
                  </p>
                </motion.div>
              )}
              {/* Checkbox "Утверждено" */}
              <div className="flex items-center justify-between p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                <div className="flex items-center gap-3">
                  <motion.label
                    whileHover={{ scale: 1.05 }}
                    className="relative inline-flex items-center cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={approved}
                      onChange={(e) => {
                        log.info(
                          "Изменено состояние 'утверждено'",
                          e.target.checked
                        );
                        setApproved(e.target.checked);
                      }}
                      className="sr-only peer"
                      disabled={isSubmitting}
                    />
                    <div
                      className="w-11 h-6 bg-gray-300 dark:bg-gray-600 rounded-full peer 
                    peer-checked:after:translate-x-full peer-checked:after:border-white 
                    after:content-[''] after:absolute after:top-[2px] after:left-[2px]
                    after:bg-white after:border-gray-300 after:border after:rounded-full 
                    after:h-5 after:w-5 after:transition-all dark:border-gray-500 peer-checked:bg-primary-500"
                    />
                  </motion.label>
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300 select-none">
                    Утверждено
                  </span>
                </div>
                {approved && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="text-primary-500 dark:text-primary-400"
                  >
                    <FaCheckCircle size={18} />
                  </motion.div>
                )}
              </div>

              {/* Загрузка файла с drag & drop */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Прикрепить документ{" "}
                  <span className="text-gray-400 dark:text-gray-500 text-xs">
                    (необязательно)
                  </span>
                </label>

                {documentFile ? (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="relative group"
                  >
                    <div className="flex items-center gap-3 p-3 sm:p-4 rounded-lg border-2 border-success-300 dark:border-success-600 bg-success-50 dark:bg-success-900/50 transition-all">
                      {/* Иконка файла */}
                      <div className="flex-shrink-0 w-10 h-10 sm:w-12 sm:h-12 rounded-lg bg-white dark:bg-gray-700 flex items-center justify-center shadow-sm border border-success-200 dark:border-success-700">
                        {getFileIcon(documentFile.name)}
                      </div>

                      {/* Информация о файле */}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-success-800 dark:text-gray-900 truncate">
                          {documentFile.name}
                        </p>
                        <p className="text-xs text-success-600 dark:text-gray-700 mt-0.5">
                          {formatFileSize(documentFile.size)}
                        </p>
                      </div>

                      {/* Кнопка удаления */}
                      <motion.button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDocumentFile(null);
                          setErrorMessage("");
                        }}
                        whileHover={{ scale: 1.1 }}
                        whileTap={{ scale: 0.9 }}
                        className="flex-shrink-0 w-8 h-8 sm:w-9 sm:h-9 rounded-lg bg-danger-100 dark:bg-danger-900/50 hover:bg-danger-200 dark:hover:bg-danger-900/70 flex items-center justify-center transition-colors border border-danger-200 dark:border-danger-800"
                        disabled={isSubmitting}
                      >
                        <FaTrash className="h-4 w-4 text-danger-600 dark:text-danger-400" />
                      </motion.button>
                    </div>
                  </motion.div>
                ) : (
                  <div
                    {...dropzoneRootProps}
                    className={`relative cursor-pointer rounded-xl border-2 border-dashed transition-all duration-200 ${
                      isDragActive
                        ? "border-primary-500 dark:border-primary-400 bg-primary-50 dark:bg-primary-900/30 scale-[1.02]"
                        : "border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/30 hover:border-primary-400 dark:hover:border-primary-500 hover:bg-gray-100 dark:hover:bg-gray-800/50"
                    } ${isSubmitting ? "opacity-50 cursor-not-allowed" : ""}`}
                  >
                    <input {...getInputProps()} disabled={isSubmitting} />
                    <div className="flex flex-col items-center justify-center p-6 sm:p-8 gap-4">
                      {/* Иконка загрузки */}
                      <div className="relative">
                        <motion.div
                          animate={
                            isDragActive
                              ? { scale: [1, 1.1, 1], rotate: [0, 5, -5, 0] }
                              : {}
                          }
                          transition={{
                            duration: 0.5,
                            repeat: isDragActive ? Infinity : 0,
                          }}
                          className={`w-14 h-14 sm:w-16 sm:h-16 rounded-full flex items-center justify-center ${
                            isDragActive
                              ? "bg-primary-100 dark:bg-primary-900/50"
                              : "bg-gray-100 dark:bg-gray-700/50"
                          } transition-colors`}
                        >
                          <FaFileUpload
                            className={`h-7 w-7 sm:h-8 sm:w-8 ${
                              isDragActive
                                ? "text-primary-600 dark:text-primary-400"
                                : "text-gray-400 dark:text-gray-500"
                            } transition-colors`}
                          />
                        </motion.div>
                      </div>

                      {/* Текст */}
                      <div className="text-center space-y-1">
                        <p className="text-sm sm:text-base font-medium text-gray-700 dark:text-gray-200">
                          {isDragActive
                            ? "Отпустите файл здесь"
                            : "Нажмите или перетащите файл"}
                        </p>
                        <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
                          PDF, JPG, JPEG, PNG
                        </p>
                        <p className="text-xs text-gray-400 dark:text-gray-500">
                          Максимальный размер: 10 МБ
                        </p>
                      </div>

                      {/* Визуальный индикатор drag & drop */}
                      {isDragActive && (
                        <motion.div
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          className="absolute inset-0 rounded-xl bg-primary-500/10 dark:bg-primary-400/10 pointer-events-none"
                        />
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Кнопки действий */}
              <div className="flex gap-2 sm:gap-3 pt-2 flex-shrink-0">
                <motion.button
                  type="button"
                  onClick={onClose}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className="flex-1 px-4 py-2.5 rounded-lg border-2 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 font-medium hover:bg-gray-50 dark:hover:bg-gray-700 transition-all"
                  disabled={isSubmitting}
                >
                  Отмена
                </motion.button>
                <motion.button
                  type="submit"
                  whileHover={!isSubmitting ? { scale: 1.02 } : {}}
                  whileTap={!isSubmitting ? { scale: 0.98 } : {}}
                  className="btn-primary flex-1 flex items-center justify-center gap-2 relative overflow-hidden"
                  disabled={isSubmitting || !!dateError}
                >
                  {isSubmitting ? (
                    <>
                      <motion.div
                        className="w-4 h-4 border-2 border-white border-t-transparent rounded-full"
                        animate={{ rotate: 360 }}
                        transition={{
                          duration: 0.8,
                          repeat: Infinity,
                          ease: "linear",
                        }}
                      />
                      <span>Сохранение...</span>
                    </>
                  ) : (
                    <>
                      <FaCheckCircle />
                      <span>Сохранить</span>
                    </>
                  )}
                </motion.button>
              </div>
            </form>
          </div>
        </motion.div>
      </div>
    </>,
    document.body
  );
};

export default NewAbsenceModal;
