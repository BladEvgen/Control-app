import React, { useEffect, useState } from "react";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { useParams } from "react-router-dom";
import { useNavigate } from "../RouterUtils";
import { CircleLoader } from "react-spinners";
import { StaffData, AttendanceData } from "../schemas/IData";

const StaffDetail = () => {
  const { pin } = useParams<{ pin: string }>();
  const [staffData, setStaffData] = useState<StaffData | null>(null);
  const [oneMonthData, setOneMonthData] = useState<StaffData | null>(null);
  const [oneMonthDataFetched, setOneMonthDataFetched] = useState(false);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
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

    fetchStaffData();
  }, [pin, startDate, endDate]);

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
      const params = {
        start_date: startDate,
        end_date: endDate,
      };
      const res = await axiosInstance.get(`${apiUrl}/api/staff/${pin}`, {
        params,
      });
      setOneMonthData(res.data);
      setOneMonthDataFetched(true);
    } catch (error) {
      console.error(`Error fetching one month data: ${error}`);
    }
  };

  const handleStartDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setStartDate(e.target.value);
    setError("");
    setEndDate("");
  };

  const handleEndDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setEndDate(e.target.value);
    setError("");
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

  const renderAttendanceRow = (date: string, data: AttendanceData) => {
    const isWeekend = data.is_weekend;
    const hasInOut = data.first_in && data.last_out;

    if (!hasInOut && !isWeekend) {
      return (
        <tr key={date} className="bg-red-100">
          <td colSpan={5} className="px-6 py-4 whitespace-nowrap">
            {date}: Нет данных
          </td>
        </tr>
      );
    } else if (!hasInOut && isWeekend) {
      return (
        <tr key={date} className="bg-yellow-100">
          <td colSpan={5} className="px-6 py-4 whitespace-nowrap">
            {date}: Выходной день
          </td>
        </tr>
      );
    } else {
      return (
        <tr key={date} className={isWeekend ? "bg-green-100" : ""}>
          <td className="px-6 py-3 whitespace-nowrap">{date}</td>
          <td className="px-6 py-3 whitespace-nowrap">
            {data.first_in ? formatDate(data.first_in) : "Нет данных"}
          </td>
          <td className="px-6 py-3 whitespace-nowrap">
            {data.last_out ? formatDate(data.last_out) : "Нет данных"}
          </td>
          <td className="px-6 py-3 whitespace-nowrap">{data.percent_day}%</td>
          <td className="px-6 py-3 whitespace-nowrap">
            {data.total_minutes
              ? formatMinutes(data.total_minutes)
              : "Нет данных"}
          </td>
        </tr>
      );
    }
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

  let bonusPercentage = 0;
  if (
    oneMonthData &&
    oneMonthData.percent_for_period &&
    staffData &&
    staffData.salary !== null
  ) {
    if (oneMonthData.percent_for_period > 70) {
      if (oneMonthData.percent_for_period >= 95) {
        bonusPercentage = 20;
      } else if (oneMonthData.percent_for_period >= 85) {
        bonusPercentage = 15;
      } else {
        bonusPercentage = 10;
      }
    }
  }

  return (
    <div className="container mx-auto p-4 sm:p-8 bg-white shadow-md rounded-lg">
      {loading ? (
        <div className="flex items-center justify-center h-full">
          <CircleLoader color="#4A90E2" loading={loading} size={50} />
        </div>
      ) : (
        staffData && (
          <div>
            <div className="flex flex-col sm:flex-row items-center">
              <img
                src={`${apiUrl}${staffData.avatar}`}
                alt="Avatar"
                className="w-32 h-32 rounded-full mb-4 sm:mr-4"
              />
              <div className="flex-grow">
                <p>
                  <strong>ФИО:</strong> {staffData.surname} {staffData.name}
                </p>
                <p>
                  <strong>Отдел:</strong> {staffData.department}
                </p>
                <p>
                  <strong>Должность:</strong>{" "}
                  {staffData.positions?.join(", ") || "Нет данных"}
                </p>
                <p>
                  <strong>Зарплата:</strong> {formatNumber(staffData.salary)}
                </p>
                <p>
                  <strong>Процент за выбранный период:</strong>{" "}
                  {staffData.percent_for_period} %
                </p>
              </div>
            </div>

            {bonusPercentage > 0 && (
              <p className="text-green-500">
                Сотрудник может получить дополнительную надбавку в размере{" "}
                {bonusPercentage}% (
                {formatNumber(
                  ((staffData.salary ?? 0) * bonusPercentage) / 100
                )}
                )
              </p>
            )}

            <h2 className="text-xl font-bold mt-6 mb-4">Посещаемость</h2>
            <div className="mb-4 flex flex-wrap justify-center sm:justify-between">
              <div className="mb-2 sm:mb-0">
                <label
                  htmlFor="startDate"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Дата начала:
                </label>
                <input
                  type="date"
                  id="startDate"
                  value={startDate}
                  onChange={handleStartDateChange}
                  className="rounded-md border-gray-300 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50 w-full sm:w-auto"
                  placeholder="Дата начала"
                />
              </div>
              {startDate && (
                <div className="mt-2 sm:mt-0">
                  <label
                    htmlFor="endDate"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Дата окончания:
                  </label>
                  <input
                    type="date"
                    id="endDate"
                    value={endDate}
                    onChange={handleEndDateChange}
                    className="rounded-md border-gray-300 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50 w-full sm:w-auto"
                    placeholder="Дата окончания"
                  />
                </div>
              )}
            </div>
            {error && <p className="text-red-500 mt-2">{error}</p>}

            <div className="overflow-x-auto">
              <table className="w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Дата
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Первое прибытие
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Последний уход
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Процент дня
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Всего времени (Ч:М)
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {Object.entries(staffData.attendance).map(([date, data]) =>
                    renderAttendanceRow(date, data)
                  )}
                </tbody>
              </table>
            </div>

            <button
              className="fixed bottom-4 left-4 bg-green-500 text-white rounded-full px-4 py-2  hover:bg-green-700 shadow-md z-10 focus:outline-none"
              onClick={navigateToChildDepartment}
            >
              <span role="img" aria-label="Back" className="text-xl">
                ◀
              </span>
            </button>
          </div>
        )
      )}
    </div>
  );
};

export default StaffDetail;
