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
  return choice ? choice[1] : type;
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
        if (loading) setLoading(false);
      }
    }
  }, [startDate, endDate, pin, isFirstLoad, loading]);

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
  let bonusPercentage = 0;
  if (
    staffData &&
    Object.keys(staffData.attendance).length > 28 &&
    Object.keys(staffData.attendance).length < 32
  ) {
    const percent_for_period = staffData.percent_for_period;
    if (percent_for_period > 125) {
      if (percent_for_period >= 145) {
        bonusPercentage = 20;
      } else if (percent_for_period >= 135) {
        bonusPercentage = 15;
      } else {
        bonusPercentage = 10;
      }
    }
  }

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
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.6 },
    },
  };

  const floatingButtonVariants = {
    hover: { scale: 1.05 },
    tap: { scale: 0.95 },
  };

  return (
    <motion.div
      className="container mx-auto p-6 sm:p-10 rounded-xl relative bg-white dark:bg-gray-900 dark:text-white"
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
          {staffData && (
            <div className="relative">
              {/* Плавающая кнопка "Назад" (мобильные) */}
              <motion.button
                variants={floatingButtonVariants}
                whileHover="hover"
                whileTap="tap"
                className="fixed bottom-4 left-4 bg-green-500 text-white 
                  rounded-full p-4 hover:bg-green-700 shadow-md z-50 
                  focus:outline-none transition-transform sm:hidden"
                onClick={navigateToChildDepartment}
              >
                <FaChevronLeft className="text-xl" />
              </motion.button>

              {/* Плавающая кнопка "Скачать Excel" (мобильные) */}
              <motion.button
                variants={floatingButtonVariants}
                whileHover="hover"
                whileTap="tap"
                onClick={handleDownloadExcel}
                disabled={!staffData}
                className={`fixed bottom-4 right-4 
                  rounded-full p-4 shadow-md z-50 focus:outline-none transition-transform
                  sm:hidden ${
                    staffData
                      ? "bg-blue-500 hover:bg-blue-700 text-white"
                      : "bg-gray-400 cursor-not-allowed text-white"
                  }`}
              >
                <BsFileEarmarkTextFill className="text-xl" />
              </motion.button>

              {/* Шапка (для планшетов и десктопов) */}
              <div className="hidden sm:flex justify-between items-center mb-4 flex-wrap">
                <motion.button
                  variants={floatingButtonVariants}
                  whileHover="hover"
                  whileTap="tap"
                  className="bg-green-500 text-white rounded-full p-3 hover:bg-green-700 shadow-md z-10 focus:outline-none"
                  onClick={navigateToChildDepartment}
                >
                  <FaChevronLeft className="text-xl" />
                </motion.button>

                <motion.button
                  variants={floatingButtonVariants}
                  whileHover="hover"
                  whileTap="tap"
                  onClick={handleDownloadExcel}
                  disabled={!staffData}
                  className={`mt-2 px-6 py-2 rounded-md text-white transition-colors ${
                    staffData
                      ? "bg-blue-500 hover:bg-blue-700"
                      : "bg-gray-400 cursor-not-allowed"
                  }`}
                >
                  Скачать Excel
                </motion.button>
              </div>

              {/* Данные о сотруднике */}
              <div className="mb-6 sm:mb-8">
                <div className="flex flex-col items-center sm:flex-row sm:items-start sm:space-x-6">
                  <motion.img
                    src={`${apiUrl}${staffData.avatar}`}
                    alt="Avatar"
                    className="w-24 h-24 sm:w-32 sm:h-32 rounded-full mb-4 sm:mb-0 shadow-md"
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.5 }}
                  />
                  <div className="text-center sm:text-left">
                    {staffData.surname && staffData.name && (
                      <p className="text-lg font-semibold mb-1">
                        <strong>ФИО:</strong> {staffData.surname}{" "}
                        {staffData.name}
                      </p>
                    )}
                    {staffData.department && (
                      <p className="text-lg font-semibold mb-1">
                        <strong>Отдел:</strong>{" "}
                        {formatDepartmentName(staffData.department)}
                      </p>
                    )}
                    {staffData.positions && staffData.positions.length > 0 && (
                      <p className="text-lg font-semibold mb-1">
                        <strong>Должность:</strong>{" "}
                        {staffData.positions.join(", ")}
                      </p>
                    )}
                    {staffData.contract_type && (
                      <p className="text-lg font-semibold mb-1">
                        <strong>Тип занятости:</strong>{" "}
                        {getContractTypeLabel(staffData.contract_type)}
                      </p>
                    )}
                    {staffData.percent_for_period !== undefined && (
                      <p className="text-lg font-semibold mb-1">
                        <strong>Процент за выбранный период:</strong>{" "}
                        {staffData.percent_for_period} %
                      </p>
                    )}
                    {Object.keys(staffData.attendance).length > 0 && (
                      <p className="text-lg mb-2">
                        <span className="inline-flex items-center">
                          <FiInfo className="mr-1 text-gray-400 dark:text-gray-500" />
                          Выбранный период: {formatDateRu(startDate)} -{" "}
                          {formatDateRu(endDate)} (найдено{" "}
                          {Object.keys(staffData.attendance).length}{" "}
                          {declensionDays(
                            Object.keys(staffData.attendance).length
                          )}
                          )
                        </span>
                      </p>
                    )}
                  </div>
                </div>
                {bonusPercentage > 0 && (
                  <motion.p
                    className="text-lg text-green-600 dark:text-green-400 mt-4"
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4 }}
                  >
                    Сотрудник может получить доплату в размере {bonusPercentage}
                    %
                  </motion.p>
                )}
              </div>

              <h2 className="text-2xl font-bold mt-8 mb-4 text-center">
                Посещаемость
              </h2>
              <div className="flex flex-wrap justify-center gap-4 text-sm text-gray-700 dark:text-gray-400 mt-4">
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
                      className="flex items-center space-x-2"
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.05, duration: 0.3 }}
                    >
                      <div
                        className={`w-4 h-4 rounded-full ${colorClass}`}
                      ></div>
                      <span className="font-semibold">{item}</span>
                    </motion.div>
                  );
                })}
              </div>
              <DateForm
                startDate={startDate}
                endDate={endDate}
                handleStartDateChange={handleStartDateChange}
                handleEndDateChange={handleEndDateChange}
                error={error}
              />

              <AttendanceTable attendance={attendance} />
            </div>
          )}
        </>
      )}
    </motion.div>
  );
};

export default StaffDetail;
