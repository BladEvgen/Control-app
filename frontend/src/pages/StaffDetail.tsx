import React, { useEffect, useState, useCallback } from "react";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { useParams } from "react-router-dom";
import { useNavigate } from "../RouterUtils";
import { StaffData, AttendanceData } from "../schemas/IData";
import { FaChevronLeft } from "react-icons/fa";
import { BsFileEarmarkTextFill } from "react-icons/bs";
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
    Object.values(attendance).forEach((data) => {
      if (data.is_weekend && !data.first_in && !data.last_out) {
        legend.add("Выходной день");
      } else if (data.is_weekend && data.first_in && data.last_out) {
        legend.add("Работа в выходной");
      } else if (data.is_remote_work) {
        legend.add("Удаленная работа");
      } else if (!data.first_in && !data.last_out) {
        if (data.is_absent_approved) {
          legend.add(`Одобрено: ${data.absent_reason || "Без причины"}`);
        } else {
          legend.add(`Не одобрено: ${data.absent_reason || "Без причины"}`);
        }
      }
    });
    return Array.from(legend);
  };

  const legendItems = generateLegendItems(attendance);
  const bonusPercentage = staffData?.bonus_percentage ?? 0;

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
      className="min-h-screen py-8 px-4 sm:px-8 lg:px-12"
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
          <motion.button
            variants={buttonVariants}
            whileHover="hover"
            whileTap="tap"
            className="fixed bottom-4 left-4 bg-green-500 hover:bg-green-600 text-white rounded-full p-4 shadow-lg z-50 focus:outline-none transition-transform sm:hidden"
            onClick={navigateToChildDepartment}
          >
            <FaChevronLeft size={24} />
          </motion.button>
          <motion.button
            variants={buttonVariants}
            whileHover="hover"
            whileTap="tap"
            onClick={handleDownloadExcel}
            className="fixed bottom-4 right-4 bg-blue-500 hover:bg-blue-600 text-white rounded-full p-4 shadow-lg z-50 focus:outline-none transition-transform sm:hidden"
          >
            <BsFileEarmarkTextFill size={24} />
          </motion.button>

          {staffData && (
            <div className="w-full max-w-7xl mx-auto bg-white dark:bg-gray-900 shadow-2xl rounded-xl overflow-hidden">
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
                <motion.button
                  variants={buttonVariants}
                  whileHover="hover"
                  whileTap="tap"
                  onClick={handleDownloadExcel}
                  className="hidden sm:flex items-center bg-blue-500 hover:bg-blue-600 text-white px-8 py-3 rounded-lg shadow transition-colors focus:outline-none"
                >
                  <BsFileEarmarkTextFill className="mr-3" size={24} />
                  Скачать Excel
                </motion.button>
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
                {bonusPercentage > 0 && (
                  <motion.div
                    variants={bonusVariants}
                    initial="hidden"
                    animate="visible"
                    className="flex items-center justify-center bg-green-100 dark:bg-green-900 rounded-lg p-6"
                  >
                    <p className="text-lg font-medium text-green-700 dark:text-green-300">
                      Бонус: {bonusPercentage}%
                    </p>
                  </motion.div>
                )}
              </div>

              {/* Дата и статистика */}
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

                {/* Легенда */}
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

                {/* Таблица посещаемости */}
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
