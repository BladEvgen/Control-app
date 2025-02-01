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
import { motion } from "framer-motion";
import LoaderComponent from "../components/LoaderComponent";

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
    new Date(new Date().setDate(new Date().getDate() - 7))
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
          params: { startDate, endDate },
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

  const containerVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.6 } },
  };
  const buttonVariants = {
    hover: { scale: 1.1, transition: { duration: 0.2 } },
    tap: { scale: 0.95, transition: { duration: 0.1 } },
  };
  const tableVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.1 } },
  };
  const rowVariants = {
    hidden: { opacity: 0, y: 10 },
    visible: { opacity: 1, y: 0 },
  };

  return (
    <motion.div
      className="mx-auto px-4 py-8 dark:text-white max-w-full md:max-w-[70vw]"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {isLoading ? (
        <LoaderComponent />
      ) : error ? (
        <div className="flex flex-col items-center justify-center min-h-screen">
          <FaTimesCircle className="text-red-500 text-5xl mb-4" />
          <p className="text-xl text-red-600 dark:text-red-400">{error}</p>
          <Link
            to="/"
            className="mt-6 px-4 py-2 bg-yellow-500 dark:bg-yellow-700 text-white text-lg rounded-lg shadow-md hover:bg-yellow-600 transition-colors duration-300 ease-in-out"
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

          {/* Верхний блок с кнопками – виден только на устройствах md и выше */}
          <div className="hidden md:flex items-end justify-between mb-6">
            <div className="flex space-x-4">
              <Link
                to="/"
                className="flex items-center px-4 py-2 bg-yellow-500 dark:bg-yellow-700 text-white text-lg rounded-lg shadow-md hover:bg-yellow-600 transition-colors duration-300 ease-in-out"
              >
                <FaHome className="mr-2" />
                <span className="font-semibold">На главную</span>
              </Link>
              <button
                onClick={navigateToChildDepartment}
                className="flex items-center px-4 py-2 bg-blue-500 text-white text-lg rounded-lg shadow-md hover:bg-blue-600 transition-colors duration-300 ease-in-out"
              >
                <FaArrowLeft className="mr-2" />
                <span>Вернуться назад</span>
              </button>
            </div>
            {/* Скрываем эту кнопку на ПК */}
            <button
              onClick={handleDownload}
              disabled={isDownloadDisabled || isDownloading}
              className="flex items-center px-4 py-2 mt-2 bg-green-500 hover:bg-green-600 text-white text-lg rounded-lg shadow-md transition-colors duration-300 ease-in-out md:hidden"
            >
              {isDownloading ? (
                <svg
                  className="animate-spin h-5 w-5 mr-2 text-white"
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
          </div>

          {/* Блок с датами и кнопкой скачать (для устройств ниже md) */}
          <div className="flex flex-col sm:flex-row md:items-end items-center sm:space-x-4 mb-4 px-2 ml">
            <div className="flex flex-col sm:flex-row sm:items-end w-full sm:w-auto space-y-4 sm:space-y-0">
              <div className="w-full sm:w-40">
                <label
                  htmlFor="startDate"
                  className="block mb-1 font-medium text-gray-200 dark:text-gray-400"
                >
                  Дата начала:
                </label>
                <input
                  type="date"
                  id="startDate"
                  value={startDate}
                  onChange={handleStartDateChange}
                  className="border border-gray-300 px-3 py-2 rounded-md w-full focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:text-white dark:border-gray-600"
                />
              </div>
            </div>
            <div className="w-full sm:w-40 mt-4 sm:mt-0">
              <label
                htmlFor="endDate"
                className="block mb-1 font-medium text-gray-200 dark:text-gray-400"
              >
                Дата конца:
              </label>
              <input
                type="date"
                id="endDate"
                value={endDate}
                onChange={handleEndDateChange}
                className="border border-gray-300 px-3 py-2 rounded-md w-full focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:text-white dark:border-gray-600"
              />
            </div>
            <div className="w-full sm:w-auto mt-4 sm:mt-0 md:self-end">
              <button
                onClick={handleDownload}
                disabled={isDownloadDisabled || isDownloading}
                className="w-full sm:w-auto px-4 py-2 bg-green-500 hover:bg-green-600 text-white text-lg rounded-lg shadow-md transition-colors duration-300 ease-in-out"
              >
                {isDownloading ? (
                  <svg
                    className="animate-spin h-5 w-5 inline mr-2 text-white"
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
                  <FaDownload className="inline mr-2" />
                )}
                {isDownloading ? "Загрузка" : "Скачать"}
              </button>
            </div>
            {showWaitMessage && (
              <motion.div
                animate={{ opacity: [1, 0.1, 1] }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  repeatType: "loop",
                  ease: "easeInOut",
                }}
                className="mt-2 p-3 bg-red-100 text-red-600 text-sm rounded-lg shadow-md dark:bg-red-900 dark:text-red-200"
              >
                Загрузка может занять некоторое время, пожалуйста, подождите...
              </motion.div>
            )}
          </div>

          {/* Инпут для поиска – во всю ширину */}
          <div className="mb-6 px-2">
            <input
              type="text"
              placeholder="Поиск по ФИО"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="border border-gray-300 px-4 py-2 rounded-md w-full focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors duration-300 ease-in-out dark:bg-gray-800 dark:text-white dark:border-gray-600"
            />
          </div>

          <p className="text-gray-300 mb-4 px-2 dark:text-gray-400">
            <strong>Количество сотрудников:</strong> {data?.staff_count}
          </p>

          {/* Мобильная версия карточек */}
          <div className="block md:hidden space-y-2">
            {data?.staff_data &&
              Object.entries(data.staff_data)
                .filter(([, staff]) =>
                  staff.FIO.toLowerCase().includes(searchQuery.toLowerCase())
                )
                .map(([pin, staff]) => (
                  <div
                    key={pin}
                    className="w-full p-6 rounded-lg shadow-md bg-white dark:bg-gray-800"
                  >
                    <div className="flex justify-between items-center mb-3">
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
                    <p className="text-gray-600 dark:text-gray-400 text-base">
                      <strong>Должность: </strong>
                      {staff.positions.length > 2
                        ? `${staff.positions[0]}, ... (ещё ${
                            staff.positions.length - 1
                          })`
                        : staff.positions.join(", ")}
                    </p>
                    <p className="text-gray-600 dark:text-gray-400 text-base mt-1">
                      <strong>Дата создания: </strong>
                      {new Date(staff.date_of_creation).toLocaleDateString()}
                    </p>
                  </div>
                ))}
          </div>

          {/* Версия для планшетов и ПК с анимацией таблицы */}
          <motion.div
            variants={tableVariants}
            initial="hidden"
            animate="visible"
            className="hidden md:block overflow-x-auto rounded-lg shadow-lg bg-white dark:bg-gray-900 px-2"
          >
            <table className="w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="w-full rounded-t-lg">
                <tr>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-blue-700 dark:text-blue-300 uppercase tracking-wider">
                    ФИО
                  </th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-blue-700 dark:text-blue-300 uppercase tracking-wider">
                    Должность
                  </th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-blue-700 dark:text-blue-300 uppercase tracking-wider">
                    Дата создания
                  </th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-blue-700 dark:text-blue-300 uppercase tracking-wider">
                    Avatar
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
                {data?.staff_data &&
                  Object.entries(data.staff_data)
                    .filter(([, staff]) =>
                      staff.FIO.toLowerCase().includes(
                        searchQuery.toLowerCase()
                      )
                    )
                    .map(([pin, staff]) => (
                      <motion.tr
                        key={pin}
                        variants={rowVariants}
                        className="hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                      >
                        <td className="px-6 py-4 whitespace-nowrap">
                          <Link
                            to={`/staffDetail/${pin}`}
                            className="text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-200"
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
                      </motion.tr>
                    ))}
              </tbody>
            </table>
          </motion.div>
        </>
      )}

      {/* Плавающие кнопки для смартфонов (видны только на экранах ниже md) */}
      <div className="block md:hidden">
        <motion.button
          variants={buttonVariants}
          whileHover="hover"
          whileTap="tap"
          className="fixed bottom-4 left-4 bg-blue-600 hover:bg-blue-700 text-white rounded-full p-4 shadow-lg z-50 focus:outline-none transition-transform"
          onClick={navigateToChildDepartment}
        >
          <FaArrowLeft size={24} />
        </motion.button>
        <motion.button
          variants={buttonVariants}
          whileHover="hover"
          whileTap="tap"
          onClick={() => navigate("/")}
          className="fixed bottom-4 right-4 bg-yellow-500 hover:bg-yellow-600 text-white rounded-full p-4 shadow-lg z-50 focus:outline-none transition-transform"
        >
          <FaHome size={24} />
        </motion.button>
      </div>
    </motion.div>
  );
};

export default ChildDepartmentPage;
