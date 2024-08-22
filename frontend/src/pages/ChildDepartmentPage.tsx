import { Link, useNavigate } from "../RouterUtils";
import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { IChildDepartmentData } from "../schemas/IData";
import { formatDepartmentName } from "../utils/utils";
import {
  FaDownload,
  FaArrowLeft,
  FaHome,
  FaCheckCircle,
  FaTimesCircle,
} from "react-icons/fa";

class BaseAction<T> {
  static SET_LOADING = "SET_LOADING";
  static SET_DATA = "SET_DATA";
  static SET_ERROR = "SET_ERROR";

  type: string;
  payload?: T;

  constructor(type: string, payload?: T) {
    this.type = type;
    this.payload = payload;
  }
}

const ChildDepartmentPage = () => {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<IChildDepartmentData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [startDate, setStartDate] = useState<string>(
    new Date(new Date().setDate(new Date().getDate() - 31))
      .toISOString()
      .split("T")[0]
  );
  const [endDate, setEndDate] = useState<string>(
    new Date().toISOString().split("T")[0]
  );
  const [isDownloading, setIsDownloading] = useState<boolean>(false);
  const [showWaitMessage, setShowWaitMessage] = useState<boolean>(false);
  const navigate = useNavigate();

  const navigateToChildDepartment = () => {
    if (data?.child_department.parent) {
      navigate(`/department/${data.child_department.parent}`);
    }
  };

  const dispatch = (action: BaseAction<any>) => {
    switch (action.type) {
      case BaseAction.SET_LOADING:
        setIsLoading(action.payload as boolean);
        break;
      case BaseAction.SET_DATA:
        setData(action.payload as IChildDepartmentData);
        setIsLoading(false);
        break;
      case BaseAction.SET_ERROR:
        setError(action.payload as string);
        setIsLoading(false);
        break;
    }
  };

  useEffect(() => {
    const fetchData = async () => {
      dispatch(new BaseAction(BaseAction.SET_LOADING, true));

      try {
        const res = await axiosInstance.get(
          `${apiUrl}/api/child_department/${id}/`
        );
        dispatch(new BaseAction(BaseAction.SET_DATA, res.data));
      } catch (error) {
        console.error(`Error: ${error}`);
        dispatch(
          new BaseAction(BaseAction.SET_ERROR, "Не удалось загрузить данные")
        );
      }
    };

    fetchData();
  }, [id]);

  const handleStartDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newStartDate = e.target.value;
    setStartDate(newStartDate);
    if (newStartDate > endDate) {
      setEndDate(newStartDate);
    }
  };

  const handleEndDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newEndDate = e.target.value;
    if (newEndDate >= startDate) {
      setEndDate(newEndDate);
    }
  };

  const handleDownload = async () => {
    setIsDownloading(true);
    setShowWaitMessage(false);

    const downloadTimeout = setTimeout(() => {
      setShowWaitMessage(true);
      const hideWaitMessage = setTimeout(() => {
        setShowWaitMessage(false);
      }, 7000);
      return () => clearTimeout(hideWaitMessage);
    }, 3000);

    try {
      const response = await axiosInstance.get(
        `${apiUrl}/api/download/${id}/`,
        {
          params: {
            startDate,
            endDate,
          },
          responseType: "blob",
          timeout: 600000,
        }
      );

      clearTimeout(downloadTimeout);
      setIsDownloading(false);
      let departmentName = "";
      if (data && data.child_department) {
        departmentName = data.child_department.name
          ? data.child_department.name.replace(/\s/g, "_")
          : data.child_department.child_id.toString();
      }

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `Посещаемость_${departmentName}.xlsx`);
      document.body.appendChild(link);
      link.click();
      if (link.parentNode) {
        link.parentNode.removeChild(link);
      }
    } catch (error) {
      console.error("Error downloading the file:", error);
      setIsDownloading(false);
    }
  };

  const isDownloadDisabled = !startDate || !endDate;

  return (
    <div className="container mx-auto px-4 py-8 dark:text-white">
      {isLoading ? (
        <div className="flex flex-col items-center justify-center h-screen">
          <div className="loader"></div>
          <p className="mt-4 text-lg text-gray-300 dark:text-gray-400">
            Данные загружаются, пожалуйста, подождите...
          </p>
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center h-screen">
          <FaTimesCircle className="text-red-500 text-5xl mb-4" />
          <p className="text-xl text-red-600 dark:text-red-400">{error}</p>
          <Link
            to="/"
            className="mt-6 px-4 py-2 bg-yellow-500 text-white text-lg rounded-lg shadow-md hover:bg-yellow-600 dark:bg-yellow-700 dark:hover:bg-yellow-800 transition-colors duration-300 ease-in-out"
          >
            Вернуться на главную
          </Link>
        </div>
      ) : (
        <>
          <h1 className="text-3xl font-bold text-center md:text-left text-white mb-8">
            {data?.child_department?.name &&
              formatDepartmentName(data.child_department.name)}
          </h1>

          <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-6">
            <div className="flex justify-center space-x-4 mt-4 md:mt-0">
              <Link
                to="/"
                className="flex items-center px-3 py-2 bg-yellow-500 text-white text-lg rounded-lg shadow-md hover:bg-yellow-600 dark:bg-yellow-700 dark:hover:bg-yellow-800 transition-colors duration-300 ease-in-out"
              >
                <FaHome className="mr-2" />
                <span className="font-semibold">На главную</span>
              </Link>
              <button
                onClick={navigateToChildDepartment}
                className="flex items-center px-3 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 dark:bg-blue-700 dark:hover:bg-blue-800 transition-colors duration-300 ease-in-out"
              >
                <FaArrowLeft className="mr-2" />
                <span>Вернуться назад</span>
              </button>
            </div>
          </div>

          <div className="flex flex-col md:flex-row md:space-x-4 mb-4">
            <div className="flex flex-col mb-4 md:mb-0">
              <label
                htmlFor="startDate"
                className="block mb-2 font-medium text-gray-200 dark:text-gray-400"
              >
                Дата начала:
              </label>
              <input
                type="date"
                id="startDate"
                value={startDate}
                onChange={handleStartDateChange}
                className="border border-gray-300 px-4 py-2 rounded-md w-full focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:text-white dark:border-gray-600"
              />
            </div>
            <div className="flex flex-col mb-4 md:mb-0">
              <label
                htmlFor="endDate"
                className="block mb-2 font-medium text-gray-200 dark:text-gray-400"
              >
                Дата конца:
              </label>
              <input
                type="date"
                id="endDate"
                value={endDate}
                onChange={handleEndDateChange}
                className="border border-gray-300 px-4 py-2 rounded-md w-full focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:text-white dark:border-gray-600"
              />
            </div>
            <div className="flex flex-col md:flex-row md:items-center">
              <button
                onClick={handleDownload}
                disabled={isDownloadDisabled || isDownloading}
                className={`flex items-center justify-center w-full md:w-auto px-4 py-2 rounded-lg text-white mt-4 md:mt-7 ${
                  isDownloadDisabled || isDownloading
                    ? "bg-gray-400 cursor-not-allowed dark:bg-gray-600"
                    : "bg-green-500 hover:bg-green-600 dark:bg-green-600 dark:hover:bg-green-700"
                } shadow-md`}
              >
                {isDownloading ? (
                  <svg
                    className="animate-spin h-5 w-5 mr-3 text-white"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    ></circle>
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8v8h8a8 8 0 11-16 0z"
                    ></path>
                  </svg>
                ) : (
                  <FaDownload className="mr-2" />
                )}
                {isDownloading ? "Загрузка" : "Скачать"}
              </button>
              {showWaitMessage && (
                <div className="mt-2 md:mt-6 md:ml-4 p-3 bg-red-100 text-red-600 text-sm rounded-lg shadow-md animate-pulse dark:bg-red-900 dark:text-red-200">
                  Загрузка может занять некоторое время, пожалуйста,
                  подождите...
                </div>
              )}
            </div>
          </div>

          <div className="mb-6">
            <input
              type="text"
              placeholder="Поиск по ФИО"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="border border-gray-300 px-4 py-2 rounded-md w-full focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors duration-300 ease-in-out dark:bg-gray-800 dark:text-white dark:border-gray-600"
            />
          </div>

          <p className="text-gray-300 mb-4 dark:text-gray-400">
            <strong>Количество сотрудников:</strong> {data?.staff_count}
          </p>

          {/* Для мобильных устройств */}
          <div className="block md:hidden space-y-4">
            {data?.staff_data &&
              Object.entries(data.staff_data)
                .filter(([, staff]) =>
                  staff.FIO.toLowerCase().includes(searchQuery.toLowerCase())
                )
                .map(([pin, staff]) => (
                  <div
                    key={pin}
                    className="p-4 bg-white dark:bg-gray-800 rounded-lg shadow-md"
                  >
                    <div className="flex justify-between items-center mb-2">
                      <Link
                        to={`/staffDetail/${pin}`}
                        className="text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-600 font-semibold text-lg"
                      >
                        {staff.FIO}
                      </Link>
                      {staff.avatar ? (
                        <FaCheckCircle
                          className="text-green-500"
                          aria-label="success"
                        />
                      ) : (
                        <FaTimesCircle
                          className="text-red-500"
                          aria-label="fail"
                        />
                      )}
                    </div>
                    <p className="text-gray-600 dark:text-gray-400">
                      <strong>Должность: </strong>
                      {staff.positions.length > 2
                        ? `${staff.positions[0]}, ... (ещё ${
                            staff.positions.length - 1
                          })`
                        : staff.positions.join(", ")}
                    </p>
                    <p className="text-gray-600 dark:text-gray-400">
                      <strong>Дата создания: </strong>
                      {new Date(staff.date_of_creation).toLocaleDateString()}
                    </p>
                  </div>
                ))}
          </div>

          {/* Для планшетов и ПК */}
          <div className="hidden md:block overflow-x-auto rounded-lg shadow-lg bg-white dark:bg-gray-900">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400">
                    ФИО
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400">
                    Должность
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400">
                    Дата создания
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400">
                    Avatar
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200 dark:bg-gray-900 dark:divide-gray-700">
                {data?.staff_data &&
                  Object.entries(data.staff_data)
                    .filter(([, staff]) =>
                      staff.FIO.toLowerCase().includes(
                        searchQuery.toLowerCase()
                      )
                    )
                    .map(([pin, staff]) => (
                      <tr key={pin}>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <Link
                            to={`/staffDetail/${pin}`}
                            className="text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-600"
                          >
                            {staff.FIO}
                          </Link>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {staff.positions.length > 2 ? (
                            <>
                              {staff.positions[0]}, ...
                              <span className="text-gray-500 dark:text-gray-400 ml-2">
                                (ещё {staff.positions.length - 1})
                              </span>
                            </>
                          ) : (
                            staff.positions.join(", ")
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          {new Date(
                            staff.date_of_creation
                          ).toLocaleDateString()}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {staff.avatar ? (
                            <FaCheckCircle
                              className="text-green-500"
                              aria-label="success"
                            />
                          ) : (
                            <FaTimesCircle
                              className="text-red-500"
                              aria-label="fail"
                            />
                          )}
                        </td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
};

export default ChildDepartmentPage;
