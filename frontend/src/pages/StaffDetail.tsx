import React, { useEffect, useState } from "react";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { useParams } from "react-router-dom";
import { useNavigate } from "../RouterUtils";
import { CircleLoader } from "react-spinners";
import { StaffData, AttendanceData } from "../schemas/IData";
import { FaChevronLeft } from "react-icons/fa";
import { FiInfo } from "react-icons/fi";
import { formatDepartmentName } from "../utils/utils";

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

  const formatDate = (dateString: string | null) => {
    if (!dateString) return "Нет данных";
    const date = new Date(dateString);
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  const formatMinutes = (totalMinutes: number) => {
    const hours = Math.floor(totalMinutes / 60);
    const minutes = Math.ceil(totalMinutes % 60);
    return `${hours}:${minutes < 10 ? "0" : ""}${minutes}`;
  };

  const renderAttendanceRow = (
    date: string,
    data: AttendanceData,
    isFirst: boolean,
    isLast: boolean
  ) => {
    const isWeekend = data.is_weekend;
    const hasInOut = data.first_in && data.last_out;

    const rowClassNames = `px-6 py-3 whitespace-nowrap ${
      isFirst ? "rounded-t-lg" : ""
    } ${isLast ? "rounded-b-lg" : ""}`;

    if (!hasInOut && !isWeekend) {
      return (
        <tr key={date} className="bg-red-200 dark:bg-red-700 dark:text-white">
          <td colSpan={5} className={rowClassNames}>
            {date}: Нет данных
          </td>
        </tr>
      );
    } else if (!hasInOut && isWeekend) {
      return (
        <tr
          key={date}
          className="bg-yellow-200 dark:bg-yellow-700 dark:text-white"
        >
          <td colSpan={5} className={rowClassNames}>
            {date}: Выходной день
          </td>
        </tr>
      );
    } else {
      return (
        <tr
          key={date}
          className={
            isWeekend
              ? "bg-green-200 dark:bg-green-700 dark:text-white"
              : "dark:text-gray-400"
          }
        >
          <td className={rowClassNames}>{date}</td>
          <td className={rowClassNames}>
            {data.first_in ? formatDate(data.first_in) : "Нет данных"}
          </td>
          <td className={rowClassNames}>
            {data.last_out ? formatDate(data.last_out) : "Нет данных"}
          </td>
          <td className={rowClassNames}>{data.percent_day}%</td>
          <td className={rowClassNames}>
            {data.total_minutes
              ? formatMinutes(data.total_minutes)
              : "Нет данных"}
          </td>
        </tr>
      );
    }
  };

  const formatDateRu = (dateString: string) => {
    const date = new Date(dateString);
    const day = date.getDate().toString().padStart(2, "0");
    const month = (date.getMonth() + 1).toString().padStart(2, "0");
    const year = date.getFullYear();
    return `${day}.${month}.${year}`;
  };

  const navigateToChildDepartment = () => {
    if (staffData) {
      navigate(`/childDepartment/${staffData.department_id}`);
    }
  };

  const formatNumber = (value: number | undefined | null): string => {
    if (value === undefined || value === null) return "Не установлена";

    const src = value.toString();
    const [out, rnd = "0"] = src.includes(".") ? src.split(".") : [src];

    const chunks = [];
    let i = out.length;
    while (i > 0) {
      chunks.unshift(out.substring(Math.max(i - 3, 0), i));
      i -= 3;
    }

    const formattedOut = chunks.join(" ");
    return `${formattedOut}.${rnd} ₸`;
  };

  const declensionDays = (daysCount: number) => {
    if (daysCount % 10 === 1 && daysCount % 100 !== 11) {
      return "день";
    } else if (
      daysCount % 10 >= 2 &&
      daysCount % 10 <= 4 &&
      (daysCount % 100 < 10 || daysCount % 100 >= 20)
    ) {
      return "дня";
    } else {
      return "дней";
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
    <div className="container mx-auto p-6 sm:p-10 bg-white shadow-lg rounded-xl dark:bg-gray-900 dark:text-white">
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
                  <p className="text-lg font-semibold mb-1">
                    <strong>ФИО:</strong> {staffData.surname} {staffData.name}
                  </p>
                  <p className="text-lg font-semibold mb-1">
                    <strong>Отдел:</strong>{" "}
                    {formatDepartmentName(staffData.department)}
                  </p>
                  <p className="text-lg font-semibold mb-1">
                    <strong>Должность:</strong>{" "}
                    {staffData.positions?.join(", ") || "Нет данных"}
                  </p>
                  {staffData.salary !== null && (
                    <p className="text-lg font-semibold mb-1">
                      <strong>Зарплата:</strong>{" "}
                      {formatNumber(staffData.salary)}
                    </p>
                  )}
                  <p className="text-lg font-semibold mb-1">
                    <strong>Процент за выбранный период:</strong>{" "}
                    {staffData.percent_for_period} %
                  </p>
                  <p className="text-lg mb-2">
                    <TooltipText
                      text={`${startDate ? startDate : oneMonthStartDate} - ${
                        endDate ? endDate : oneMonthEndDate
                      }`}
                      daysCount={Object.keys(staffData.attendance).length}
                    />
                  </p>
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

            <div className="mb-4 flex flex-col sm:flex-row sm:space-x-4 justify-center sm:justify-between items-center sm:items-end">
              <div className="mb-2 sm:mb-0 w-full sm:w-auto">
                <label
                  htmlFor="startDate"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-400 mb-1"
                >
                  Дата начала:
                </label>
                <input
                  type="date"
                  id="startDate"
                  value={startDate}
                  onChange={handleStartDateChange}
                  className="rounded-md border-gray-300 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50 w-full sm:w-auto transition-colors duration-300 dark:bg-gray-800 dark:text-white dark:border-gray-600"
                  placeholder="Дата начала"
                />
              </div>
              {startDate && (
                <div className="mt-2 sm:mt-0 w-full sm:w-auto">
                  <label
                    htmlFor="endDate"
                    className="block text-sm font-medium text-gray-700 dark:text-gray-400 mb-1"
                  >
                    Дата окончания:
                  </label>
                  <input
                    type="date"
                    id="endDate"
                    value={endDate}
                    onChange={handleEndDateChange}
                    className="rounded-md border-gray-300 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50 w-full sm:w-auto transition-colors duration-300 dark:bg-gray-800 dark:text-white dark:border-gray-600"
                    placeholder="Дата окончания"
                  />
                </div>
              )}
            </div>
            {error && (
              <p className="text-red-600 dark:text-red-400 mt-2">{error}</p>
            )}

            <div className="overflow-x-auto">
              <table className="w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-800">
                  <tr>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400"
                    >
                      Дата
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400"
                    >
                      Первое прибытие
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400"
                    >
                      Последний уход
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400"
                    >
                      Процент дня
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400"
                    >
                      Всего времени (Ч:М)
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200 dark:bg-gray-900 dark:divide-gray-700">
                  {Object.entries(staffData.attendance)
                    .reverse()
                    .map(([date, data], index, array) =>
                      renderAttendanceRow(
                        date,
                        data,
                        index === 0,
                        index === array.length - 1
                      )
                    )}
                </tbody>
              </table>
            </div>
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
