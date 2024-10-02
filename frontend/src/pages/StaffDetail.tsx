import React, { useEffect, useState, useCallback } from "react";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { useParams } from "react-router-dom";
import { useNavigate } from "../RouterUtils";
import { StaffData, AttendanceData } from "../schemas/IData";
import { FaChevronLeft } from "react-icons/fa";
import { FiInfo } from "react-icons/fi";
import { formatDepartmentName } from "../utils/utils";
import Notification from "../components/Notification";
import DateForm from "./DateForm";
import AttendanceTable from "./AttendanceTable";
import { formatDateRu, formatNumber, declensionDays } from "../utils/utils";

const CONTRACT_TYPE_CHOICES = [
  ["full_time", "Полная занятость"],
  ["part_time", "Частичная занятость"],
  ["gph", "ГПХ"],
];

const getContractTypeLabel = (type: string): string => {
  const choice = CONTRACT_TYPE_CHOICES.find(([key]) => key === type);
  return choice ? choice[1] : type;
};

const StaffDetail = () => {
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

  let bonusPercentage = 0;
  if (
    staffData &&
    staffData.contract_type !== "gph" &&
    staffData.salary !== null &&
    Object.keys(staffData.attendance).length > 28 &&
    Object.keys(staffData.attendance).length < 32
  ) {
    const percent_for_period = staffData.percent_for_period;

    if (percent_for_period > 106) {
      if (percent_for_period > 100) {
        if (percent_for_period >= 119) {
          bonusPercentage = 20;
        } else if (percent_for_period >= 113) {
          bonusPercentage = 15;
        } else {
          bonusPercentage = 10;
        }
      }
    }
  }

  const TooltipText: React.FC<{ text: string; daysCount: number }> = ({
    text,
    daysCount,
  }) => {
    const [startDate, endDate] = text.split(" - ");
    return (
      <span className="text-sm text-gray-500 dark:text-gray-400 italic ml-2">
        <FiInfo className="inline-block align-middle mb-1 mr-1" />
        Выбранный период: {formatDateRu(startDate)} - {formatDateRu(endDate)}{" "}
        (найдено {daysCount} {declensionDays(daysCount)})
      </span>
    );
  };

  return (
    <div className="container mx-auto p-6 sm:p-10 rounded-xl relative bg-white dark:bg-gray-900 dark:text-white">
      {loading ? (
        <div className="flex flex-col items-center justify-center h-screen">
          <div className="loader"></div>
          <p className="mt-4 text-lg text-gray-300 dark:text-gray-400">
            Данные загружаются, пожалуйста, подождите...
          </p>
        </div>
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
            <div>
              <div className="relative mb-6">
                <div className="flex flex-col items-center sm:flex-row sm:items-start sm:space-x-6">
                  <img
                    src={`${apiUrl}${staffData.avatar}`}
                    alt="Avatar"
                    className="w-24 h-24 sm:w-32 sm:h-32 rounded-full mb-4 sm:mb-0 shadow-md"
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
                    {staffData.salary !== null && (
                      <p className="text-lg font-semibold mb-1">
                        <strong>Зарплата:</strong>{" "}
                        {formatNumber(staffData.salary)}
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
                        <TooltipText
                          text={`${startDate} - ${endDate}`}
                          daysCount={Object.keys(staffData.attendance).length}
                        />
                      </p>
                    )}
                  </div>
                  <button
                    className="hidden lg:block absolute left-0 top-0 sm:left-8 sm:top-8 lg:-left-14 lg:-top-4 bg-green-500 text-white rounded-full p-2 sm:p-3 hover:bg-green-700 shadow-md z-10 focus:outline-none transition-transform transform hover:scale-105"
                    onClick={navigateToChildDepartment}
                  >
                    <FaChevronLeft className="text-lg sm:text-xl" />
                  </button>
                </div>
                {bonusPercentage > 0 && (
                  <p className="text-lg text-green-600 dark:text-green-400 mt-4">
                    Сотрудник может получить премию в размере {bonusPercentage}%
                    (
                    {formatNumber(
                      ((staffData.salary ?? 0) * bonusPercentage) / 100
                    )}
                    )
                  </p>
                )}
              </div>

              <h2 className="text-2xl font-bold mt-8 mb-4 text-center">
                Посещаемость
              </h2>

              <div className="flex flex-wrap justify-center gap-4 text-sm text-gray-700 dark:text-gray-400 mt-4">
                <div className="flex items-center space-x-2">
                  <div className="w-4 h-4 rounded-full bg-yellow-400 dark:bg-yellow-500"></div>
                  <span className="font-semibold">Выходной день</span>
                </div>
                <div className="flex items-center space-x-2">
                  <div className="w-4 h-4 rounded-full bg-red-400 dark:bg-red-500"></div>
                  <span className="font-semibold">Работник отсутствовал</span>
                </div>
                <div className="flex items-center space-x-2">
                  <div className="w-4 h-4 rounded-full bg-green-400 dark:bg-green-500"></div>
                  <span className="font-semibold">
                    Работник был на работе в выходной
                  </span>
                </div>
              </div>

              <DateForm
                startDate={startDate}
                endDate={endDate}
                handleStartDateChange={handleStartDateChange}
                handleEndDateChange={handleEndDateChange}
                error={error}
              />

              <AttendanceTable attendance={attendance} />

              <button
                className="fixed bottom-4 left-4 bg-green-500 text-white rounded-full px-4 py-4 hover:bg-green-700 shadow-md z-10 focus:outline-none sm:block md:block lg:hidden"
                onClick={navigateToChildDepartment}
              >
                <FaChevronLeft className="text-xl" />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default StaffDetail;
