import React, { useEffect, useState } from "react";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { useParams } from "react-router-dom";
import { useNavigate } from "../RouterUtils";
import { CircleLoader } from "react-spinners";
import { StaffData } from "../schemas/IData";
import { FaChevronLeft } from "react-icons/fa";
import { FiInfo } from "react-icons/fi";
import { formatDepartmentName } from "../utils/utils";

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
  const [oneMonthDataFetched, setOneMonthDataFetched] = useState(false);
  const [startDate, setStartDate] = useState<string>(
    new Date(new Date().setDate(new Date().getDate() - 31))
      .toISOString()
      .split("T")[0]
  );
  const [endDate, setEndDate] = useState<string>(
    new Date(new Date().setDate(new Date().getDate() - 0))
      .toISOString()
      .split("T")[0]
  );
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [oneMonthStartDate, setOneMonthStartDate] = useState<string>("");
  const [oneMonthEndDate, setOneMonthEndDate] = useState<string>("");
  const navigate = useNavigate();

  useEffect(() => {
    const fetchStaffData = async () => {
      try {
        let params: any = {};
        if (startDate && endDate) {
          if (new Date(startDate) > new Date(endDate)) {
            setError("Дата начала не может быть позже даты окончания");
            return;
          }
          params = {
            start_date: startDate,
            end_date: endDate,
          };
        } else {
          params = {
            start_date: oneMonthStartDate,
            end_date: oneMonthEndDate,
          };
        }
        const res = await axiosInstance.get(`${apiUrl}/api/staff/${pin}`, {
          params,
        });
        setStaffData(res.data);
        setLoading(false);
      } catch (error) {
        console.error(`Error fetching staff data: ${error}`);
      }
    };

    if (oneMonthStartDate && oneMonthEndDate) {
      fetchStaffData();
    }
  }, [pin, startDate, endDate, oneMonthStartDate, oneMonthEndDate]);

  useEffect(() => {
    if (!oneMonthDataFetched) {
      fetchOneMonthData();
    }
  }, [oneMonthDataFetched]);

  const fetchOneMonthData = async () => {
    try {
      const endDate = new Date().toISOString().split("T")[0];
      const startDate = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000)
        .toISOString()
        .split("T")[0];
      setOneMonthStartDate(startDate);
      setOneMonthEndDate(endDate);
      const params = {
        start_date: startDate,
        end_date: endDate,
      };
      const res = await axiosInstance.get(`${apiUrl}/api/staff/${pin}`, {
        params,
      });
      setOneMonthDataFetched(true);

      if (res.data && res.data.percent_for_period) {
        setStaffData({
          ...res.data,
          percent_for_period: res.data.percent_for_period,
        });
      }
    } catch (error) {
      console.error(`Error fetching one month data: ${error}`);
    }
  };

  const handleStartDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newStartDate = e.target.value;
    setStartDate(newStartDate);
    if (new Date(newStartDate) > new Date(endDate)) {
      setError("");
      setEndDate(newStartDate);
    }
  };

  const handleEndDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newEndDate = e.target.value;
    setEndDate(newEndDate);
    if (new Date(newEndDate) < new Date(startDate)) {
      setError("");
      setEndDate(startDate);
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

  const navigateToChildDepartment = () => {
    if (staffData) {
      navigate(`/childDepartment/${staffData.department_id}`);
    }
  };

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
    <div className="container mx-auto p-6 sm:p-10 bg-white shadow-lg rounded-xl dark:bg-gray-900 dark:text-white relative">
      {loading ? (
        <div className="flex items-center justify-center h-full">
          <CircleLoader color="#4A90E2" loading={loading} size={50} />
        </div>
      ) : (
        staffData && (
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
                      <strong>ФИО:</strong> {staffData.surname} {staffData.name}
                    </p>
                  )}
                  {staffData.department && (
                    <p className="text-lg font-semibold mb-1">
                      <strong>Отдел:</strong>{" "}
                      {formatDepartmentName(staffData.department)}
                    </p>
                  )}
                  {staffData.positions?.length && (
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
                        text={`${startDate ? startDate : oneMonthStartDate} - ${
                          endDate ? endDate : oneMonthEndDate
                        }`}
                        daysCount={Object.keys(staffData.attendance).length}
                      />
                    </p>
                  )}
                </div>
                <button
                  className="absolute left-0 top-0 sm:left-8 sm:top-8 lg:-left-14 lg:-top-4 bg-green-500 text-white rounded-full p-2 sm:p-3 hover:bg-green-700 shadow-md z-10 focus:outline-none transition-transform transform hover:scale-105 hidden lg:block"
                  onClick={navigateToChildDepartment}
                >
                  <FaChevronLeft className="text-lg sm:text-xl" />
                </button>
              </div>
            </div>

            {bonusPercentage > 0 && (
              <p className="text-lg text-green-600 dark:text-green-400 mt-4">
                Сотрудник может получить премию в размере {bonusPercentage}% (
                {formatNumber(
                  ((staffData.salary ?? 0) * bonusPercentage) / 100
                )}
                )
              </p>
            )}
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

            <AttendanceTable attendance={staffData.attendance} />

            <button
              className="fixed bottom-4 left-4 bg-green-500 text-white rounded-full px-4 py-4 hover:bg-green-700 shadow-md z-10 focus:outline-none sm:block md:block lg:hidden"
              onClick={navigateToChildDepartment}
            >
              <FaChevronLeft className="text-xl" />
            </button>
          </div>
        )
      )}
    </div>
  );
};

export default StaffDetail;
