import React, { useEffect, useState, useCallback } from "react";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { useParams } from "react-router-dom";
import { useNavigate } from "../RouterUtils";
import { StaffData, AttendanceData } from "../schemas/IData";
import { FaChevronLeft, FaArchive } from "react-icons/fa";
import { BsFileEarmarkTextFill, BsPlusLg } from "react-icons/bs";
import { FiInfo } from "react-icons/fi";
import Notification from "../components/Notification";
import DateForm from "./DateForm";
import AttendanceTable from "./AttendanceTable";
import {
  formatDepartmentName,
  formatDateRu,
  declensionDays,
} from "../utils/utils";
import { motion } from "framer-motion";
import { generateAndDownloadExcel } from "../utils/excelUtils";
import LoaderComponent from "../components/LoaderComponent";
import NewAbsenceModal from "../components/NewAbsenceModal";

const shouldShowBonus = (staffData: StaffData | null): boolean => {
  if (!staffData) return false;
  if (staffData.bonus_percentage <= 0) return false;
  const excludedContractTypes = ["gph", "part_time"];
  return !!(
    staffData.contract_type &&
    !excludedContractTypes.includes(staffData.contract_type)
  );
};

const CONTRACT_TYPE_CHOICES: [string, string][] = [
  ["full_time", "Полная занятость"],
  ["part_time", "Частичная занятость"],
  ["gph", "ГПХ"],
];

const getContractTypeLabel = (type: string): string => {
  const choice = CONTRACT_TYPE_CHOICES.find(([key]) => key === type);
  return choice ? choice[1] : "Не указан";
};

const StaffDetail: React.FC = () => {
  const { pin } = useParams<{ pin: string }>();
  const [staffData, setStaffData] = useState<StaffData | null>(null);
  const [attendance, setAttendance] = useState<Record<string, AttendanceData>>(
    {}
  );

  const [startDate, setStartDate] = useState<string>(
    new Date(new Date().setDate(new Date().getDate() - 7))
      .toISOString()
      .split("T")[0]
  );
  const [endDate, setEndDate] = useState<string>(
    new Date().toISOString().split("T")[0]
  );
  const [error] = useState("");
  const [notificationMessage, setNotificationMessage] = useState("");
  const [notificationType, setNotificationType] = useState<"warning" | "error">(
    "error"
  );
  const [showNotification, setShowNotification] = useState(false);
  const [loading, setLoading] = useState(true);
  const [isFirstLoad, setIsFirstLoad] = useState(true);
  const [showAbsenceModal, setShowAbsenceModal] = useState(false);
  const navigate = useNavigate();

  const fetchAttendanceData = useCallback(async () => {
    if (startDate && endDate && new Date(startDate) <= new Date(endDate)) {
      if (isFirstLoad) {
        setLoading(true);
        setIsFirstLoad(false);
      }
      try {
        const params = { start_date: startDate, end_date: endDate };
        const res = await axiosInstance.get(`${apiUrl}/api/staff/${pin}`, {
          params,
        });
        setStaffData(res.data);
        setAttendance(res.data.attendance);
      } catch (error: any) {
        if (error.response && error.response.status === 404) {
          setNotificationMessage("Сотрудник не найден");
          setNotificationType("error");
          setShowNotification(true);
        } else {
          setNotificationMessage("Произошла ошибка при загрузке данных.");
          setNotificationType("error");
          setShowNotification(true);
          console.error(`Error fetching attendance data: ${error}`);
        }
      } finally {
        setLoading(false);
      }
    }
  }, [startDate, endDate, pin, isFirstLoad]);

  useEffect(() => {
    fetchAttendanceData();
  }, [startDate, endDate, fetchAttendanceData]);

  const handleStartDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newStartDate = e.target.value;
    setStartDate(newStartDate);
    if (new Date(newStartDate) > new Date(endDate)) {
      setEndDate(newStartDate);
    }
  };

  const handleEndDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newEndDate = e.target.value;
    setEndDate(newEndDate);
    if (new Date(newEndDate) < new Date(startDate)) {
      setStartDate(newEndDate);
    }
  };

  const navigateToChildDepartment = () => {
    if (staffData) {
      navigate(`/childDepartment/${staffData.department_id}`);
    }
  };

  const generateLegendItems = (attendance: Record<string, AttendanceData>) => {
    const legend = new Set<string>();
    const defaultText = "Отсутствует (Не одобрено)";

    Object.values(attendance).forEach((data) => {
      // 1. Если день отмечен как удалённая работа:
      if (data.is_remote_work) {
        legend.add("Удаленная работа");
      }
      // 2. Если указана причина отсутствия (независимо от наличия времени):
      else if (data.absent_reason && data.absent_reason.trim() !== "") {
        legend.add(
          data.is_absent_approved
            ? `Одобрено: ${data.absent_reason}`
            : `Не одобрено: ${data.absent_reason}`
        );
      }
      // 3. Если день является выходным:
      else if (data.is_weekend) {
        if (
          data.first_in &&
          data.first_in.trim() !== "" &&
          data.last_out &&
          data.last_out.trim() !== ""
        ) {
          legend.add("Работа в выходной");
        } else {
          legend.add("Выходной день");
        }
      }
      // 4. Если у рабочего дня отсутствуют данные по приходу или уходу – выводим значение по умолчанию:
      else if (
        !data.first_in ||
        data.first_in.trim() === "" ||
        !data.last_out ||
        data.last_out.trim() === ""
      ) {
        legend.add(defaultText);
      }
    });

    return Array.from(legend);
  };

  const legendItems = generateLegendItems(attendance);

  const handleDownloadExcel = async () => {
    if (!staffData) return;
    try {
      await generateAndDownloadExcel(staffData, startDate, endDate);
    } catch (error) {
      console.error("Ошибка при генерации Excel:", error);
      setNotificationMessage("Не удалось создать Excel-файл.");
      setNotificationType("error");
      setShowNotification(true);
    }
  };

  const handleDownloadZip = async () => {
    if (!staffData) return;
    try {
      const res = await axiosInstance.get(`${apiUrl}/api/absent_staff/`, {
        params: {
          start_date: startDate,
          end_date: endDate,
          staff_pin: pin,
          download: "true",
        },
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: "application/zip" });
      const link = document.createElement("a");
      link.href = window.URL.createObjectURL(blob);
      link.download = `documents_${startDate}_${endDate}.zip`;
      link.click();
    } catch (error) {
      console.error("Ошибка при скачивании ZIP:", error);
      setNotificationMessage("Не удалось скачать архив отсутствий.");
      setNotificationType("error");
      setShowNotification(true);
    }
  };

  const hasAbsenceWithReason = () => {
    return Object.values(attendance).some(
      (record) => record.absent_reason && record.absent_reason.trim() !== ""
    );
  };

  const containerVariants = {
    hidden: { opacity: 0, y: 30 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.8 } },
  };

  const buttonVariants = {
    hover: { scale: 1.1, transition: { duration: 0.2 } },
    tap: { scale: 0.95, transition: { duration: 0.1 } },
  };

  const bonusVariants = {
    hidden: { opacity: 0, scale: 0.9 },
    visible: { opacity: 1, scale: 1, transition: { duration: 0.5 } },
  };

  return (
    <motion.div
      className="min-h-screen py-8 px-4 sm:px-8 lg:px-24"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {loading ? (
        <LoaderComponent />
      ) : (
        <>
          {showNotification && (
            <Notification
              message={notificationMessage}
              type={notificationType}
              link="/"
            />
          )}

          {/* Плавающие кнопки для мобильных */}
          <div className="sm:hidden fixed bottom-4 left-4 right-4 flex justify-between z-50">
            {/* Кнопка назад */}
            <motion.button
              variants={buttonVariants}
              whileHover="hover"
              whileTap="tap"
              onClick={navigateToChildDepartment}
              className="bg-green-500 hover:bg-green-600 text-white rounded-full p-4 shadow-lg focus:outline-none transition-transform"
            >
              <FaChevronLeft size={24} />
            </motion.button>
            {/* Кнопка добавить отсутствие – расположена по центру */}
            <motion.button
              variants={buttonVariants}
              whileHover="hover"
              whileTap="tap"
              onClick={() => setShowAbsenceModal(true)}
              className="bg-gradient-to-r from-blue-900 to-blue-600 text-white rounded-full p-4 shadow-lg focus:outline-none transition-transform"
            >
              <BsPlusLg size={24} />
            </motion.button>
            {/* Кнопка скачать Excel – всегда видна */}
            <motion.button
              variants={buttonVariants}
              whileHover="hover"
              whileTap="tap"
              onClick={handleDownloadExcel}
              className="bg-green-600 hover:bg-green-700 text-white rounded-full p-4 shadow-lg focus:outline-none transition-transform"
            >
              <BsFileEarmarkTextFill size={24} />
            </motion.button>
          </div>
          {/* Для мобильных: кнопка скачать ZIP  */}
          {hasAbsenceWithReason() && (
            <motion.button
              variants={buttonVariants}
              whileHover="hover"
              whileTap="tap"
              onClick={handleDownloadZip}
              className="sm:hidden fixed bottom-20 right-4 bg-orange-600 hover:bg-orange-700 text-white rounded-full p-4 shadow-lg z-50 focus:outline-none transition-transform"
            >
              <FaArchive size={24} />
            </motion.button>
          )}

          {/* Модальное окно для создания записи отсутствия */}
          {showAbsenceModal && pin && (
            <NewAbsenceModal
              staffPin={pin}
              onClose={() => setShowAbsenceModal(false)}
              onSuccess={() => fetchAttendanceData()}
            />
          )}

          {staffData && (
            <div className="w-full max-w-7xl lg:max-w-screen-2xl mx-auto bg-white dark:bg-gray-900 shadow-2xl rounded-xl overflow-hidden">
              {/* Header */}
              <div className="flex flex-col sm:flex-row items-center justify-between p-8 border-b border-gray-200 dark:border-gray-700">
                <div className="flex items-center space-x-6">
                  <motion.button
                    variants={buttonVariants}
                    whileHover="hover"
                    whileTap="tap"
                    onClick={navigateToChildDepartment}
                    className="hidden sm:block text-green-500 hover:text-green-600 focus:outline-none"
                  >
                    <FaChevronLeft size={28} />
                  </motion.button>
                  <div className="w-28 h-28 rounded-full overflow-hidden shadow-xl">
                    <img
                      src={`${apiUrl}${staffData.avatar}`}
                      alt="Avatar"
                      className="object-cover w-full h-full"
                    />
                  </div>
                  <div>
                    <h2 className="text-4xl font-bold text-gray-800 dark:text-gray-100">
                      {staffData.surname} {staffData.name}
                    </h2>
                    {staffData.department && (
                      <p className="text-lg text-gray-500 dark:text-gray-400">
                        {formatDepartmentName(staffData.department)}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center space-x-4">
                  {/* Кнопка скачать Excel (десктоп) */}
                  <motion.button
                    variants={buttonVariants}
                    whileHover="hover"
                    whileTap="tap"
                    onClick={handleDownloadExcel}
                    className="hidden sm:flex items-center bg-green-600 hover:bg-green-700 text-white px-6 py-3 rounded-lg shadow transition-colors focus:outline-none"
                  >
                    <BsFileEarmarkTextFill className="mr-3" size={24} />
                    Скачать Excel
                  </motion.button>
                  {/* Кнопка скачать ZIP (десктоп) */}
                  {hasAbsenceWithReason() && (
                    <motion.button
                      variants={buttonVariants}
                      whileHover="hover"
                      whileTap="tap"
                      onClick={handleDownloadZip}
                      className="hidden sm:flex items-center bg-orange-600 hover:bg-orange-700 text-white px-6 py-3 rounded-lg shadow transition-colors focus:outline-none"
                    >
                      <FaArchive className="mr-3" size={24} />
                      Скачать ZIP
                    </motion.button>
                  )}
                  {/* Кнопка добавить отсутствие (десктоп) */}
                  <motion.button
                    variants={buttonVariants}
                    whileHover="hover"
                    whileTap="tap"
                    onClick={() => setShowAbsenceModal(true)}
                    className="hidden sm:flex items-center bg-gradient-to-r from-blue-900 to-blue-600 text-white px-6 py-3 rounded-lg shadow transition-colors focus:outline-none"
                  >
                    <BsPlusLg className="mr-3" size={24} />
                    Добавить отсутствие
                  </motion.button>
                </div>
              </div>

              {/* Информация о сотруднике */}
              <div className="p-8 grid grid-cols-1 md:grid-cols-2 gap-8">
                <div>
                  <p className="text-xl text-gray-700 dark:text-gray-300">
                    <strong>Должность:</strong> {staffData.positions.join(", ")}
                  </p>
                  <p className="text-xl text-gray-700 dark:text-gray-300 mt-2">
                    <strong>Тип занятости:</strong>{" "}
                    {getContractTypeLabel(staffData.contract_type || "")}
                  </p>
                  <p className="text-xl text-gray-700 dark:text-gray-300 mt-2">
                    <strong>Процент за период:</strong>{" "}
                    {staffData.percent_for_period}%
                  </p>
                </div>
                {shouldShowBonus(staffData) && (
                  <motion.div
                    variants={bonusVariants}
                    initial="hidden"
                    animate="visible"
                    className="flex items-center justify-center bg-green-100 dark:bg-green-900 rounded-lg p-6"
                  >
                    <p className="text-lg font-medium text-green-700 dark:text-green-300">
                      Бонус: {staffData.bonus_percentage}%
                    </p>
                  </motion.div>
                )}
              </div>
              {/* Остальная информация */}
              <div className="px-8 pb-8 border-t border-gray-200 dark:border-gray-700">
                <div className="flex flex-col lg:flex-row items-center justify-between mb-6 gap-6">
                  <div className="w-full max-w-md">
                    <DateForm
                      startDate={startDate}
                      endDate={endDate}
                      handleStartDateChange={handleStartDateChange}
                      handleEndDateChange={handleEndDateChange}
                      error={error}
                    />
                  </div>
                  <div className="flex flex-col items-center lg:items-end">
                    <span className="inline-flex items-center text-lg text-gray-600 dark:text-gray-400">
                      <FiInfo className="mr-2" />
                      {formatDateRu(startDate)} - {formatDateRu(endDate)}
                    </span>
                    <span className="mt-1 text-xl font-semibold text-gray-800 dark:text-gray-100">
                      Найдено {Object.keys(staffData.attendance).length}{" "}
                      {declensionDays(Object.keys(staffData.attendance).length)}
                    </span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 mb-6">
                  {legendItems.map((item, index) => {
                    let colorClass = "";
                    if (item === "Выходной день") {
                      colorClass = "bg-amber-400 dark:bg-amber-500";
                    } else if (item.includes("Работа в выходной")) {
                      colorClass = "bg-green-400 dark:bg-green-500";
                    } else if (item.includes("Удаленная работа")) {
                      colorClass = "bg-sky-400 dark:bg-sky-500";
                    } else if (item.includes("Одобрено")) {
                      colorClass = "bg-violet-400 dark:bg-violet-500";
                    } else if (item.includes("Не одобрено")) {
                      colorClass = "bg-rose-400 dark:bg-rose-500";
                    } else if (item === "Нет данных") {
                      colorClass = "bg-red-400 dark:bg-red-500";
                    } else {
                      colorClass = "bg-gray-400 dark:bg-gray-500";
                    }
                    return (
                      <motion.div
                        key={index}
                        className={`flex items-center space-x-2 px-4 py-1 rounded-full text-white text-sm ${colorClass}`}
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.05, duration: 0.3 }}
                      >
                        <div className="w-2 h-2 rounded-full bg-white"></div>
                        <span>{item}</span>
                      </motion.div>
                    );
                  })}
                </div>
                <AttendanceTable attendance={attendance} />
              </div>
            </div>
          )}
        </>
      )}
    </motion.div>
  );
};

export default StaffDetail;
