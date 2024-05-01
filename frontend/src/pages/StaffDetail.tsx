import React, { useEffect, useState } from "react";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { useParams, useNavigate } from "react-router-dom";
import { CircleLoader } from "react-spinners";
import { StaffData, AttendanceData } from "../schemas/IData";

const StaffDetail = () => {
  const { pin } = useParams<{ pin: string }>();
  const [staffData, setStaffData] = useState<StaffData | null>(null);
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

  const handleStartDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setStartDate(e.target.value);
    setError("");
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
    const isWeekend = [0, 6].includes(new Date(date).getDay());
    if (!data.first_in && !data.last_out && isWeekend) {
      return (
        <tr key={date}>
          <td colSpan={5} className="px-6 py-4 whitespace-nowrap">
            Выходной день
          </td>
        </tr>
      );
    } else {
      return (
        <tr key={date} className={isWeekend ? "bg-gray-100" : ""}>
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

  return (
    <div className="m-8">
      {loading ? ( // Проверяем состояние loading
        <div className="flex items-center justify-center h-full">
          <CircleLoader color="#4A90E2" loading={loading} size={50} />{" "}
          {/* Добавляем CircleLoader */}
        </div>
      ) : (
        staffData && ( // Проверяем, что staffData не null
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
                  <strong>Должность:</strong> {staffData.positions.join(", ")}
                </p>
                <p>
                  <strong>Зарплата:</strong>{" "}
                  {staffData.salary !== null
                    ? staffData.salary + " ₸"
                    : "Не установлена"}
                </p>
                <p>
                  <strong>Процент за выбранный период:</strong>{" "}
                  {staffData.percent_for_period} %
                </p>
              </div>
            </div>

            <h2 className="text-xl font-bold mt-6 mb-4">Посещаемость</h2>
            <div className="mb-4 flex flex-wrap justify-center sm:justify-between">
              <div className="mb-2 sm:mb-0">
                <label htmlFor="endDate" className="mr-2">
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
              <div>
                <label htmlFor="startDate" className="mr-2 sm:ml-4">
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
              {error && <p className="text-red-500 mt-2">{error}</p>}
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Дата
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Первый вход
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Последний выход
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Процент за день на работе
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Часов
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(staffData.attendance).map(([date, data]) =>
                    renderAttendanceRow(date, data)
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )
      )}

      <button
        className="fixed bottom-4 left-4 bg-gray-200 rounded-full p-3 hover:bg-gray-300 shadow-md z-10 focus:outline-none"
        onClick={navigateToChildDepartment}>
        <span role="img" aria-label="Back" className="text-xl">
          🔙
        </span>
      </button>
    </div>
  );
};

export default StaffDetail;
