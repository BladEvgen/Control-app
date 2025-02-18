import { Link, useNavigate } from "../RouterUtils";
import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { IChildDepartmentData } from "../schemas/IData";
import { formatDepartmentName } from "../utils/utils";
import {
  FaCheckCircle,
  FaTimesCircle,
  FaArrowLeft,
  FaHome,
} from "react-icons/fa";
import { motion } from "framer-motion";
import LoaderComponent from "../components/LoaderComponent";
import FloatingButton from "../components/FloatingButton";

import DesktopNavigation from "../components/DesktopNavigation";
import DateFilterBar from "../components/DateFilterBar";
import SearchInput from "../components/SearchInput";
import WaitNotification from "../components/WaitNotification";
import useWaitNotification from "../hooks/useWaitNotification";
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

  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const initialEndDate = yesterday.toISOString().split("T")[0];

  const sevenDaysAgo = new Date(yesterday);
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
  const initialStartDate = sevenDaysAgo.toISOString().split("T")[0];

  const [startDate, setStartDate] = useState<string>(initialStartDate);
  const [endDate, setEndDate] = useState<string>(initialEndDate);
  const today = new Date().toISOString().split("T")[0];

  const [isDownloading, setIsDownloading] = useState<boolean>(false);
  const navigate = useNavigate();

  const { showWaitMessage, startWaitNotification, clearWaitNotification } =
    useWaitNotification();

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
      default:
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
      } catch (err) {
        console.error("Error:", err);
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

  const navigateToChildDepartment = () => {
    if (data?.child_department.parent) {
      navigate(`/department/${data.child_department.parent}`);
    }
  };

  const handleDownload = async () => {
    setIsDownloading(true);
    startWaitNotification();

    try {
      const response = await axiosInstance.get(
        `${apiUrl}/api/download/${id}/`,
        {
          params: { startDate, endDate },
          responseType: "blob",
          timeout: 600000,
        }
      );
      clearWaitNotification();
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
      link.remove();
    } catch (error) {
      console.error("Error downloading the file:", error);
      clearWaitNotification();
      setIsDownloading(false);
    }
  };

  const isDownloadDisabled = !startDate || !endDate;

  const tableVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.1 } },
  };
  const rowVariants = {
    hidden: { opacity: 0, scale: 0.98 },
    visible: {
      opacity: 1,
      scale: 1,
      transition: { duration: 0.3, ease: "easeOut" },
    },
  };

  const containerVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.6 } },
  };

  return (
    <motion.div
      className="mx-auto px-4 py-8 dark:text-white container"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {isLoading ? (
        <LoaderComponent />
      ) : error ? (
        <div className="flex flex-col items-center justify-center min-h-screen">
          <div className="text-red-500 text-5xl mb-4">
            <FaTimesCircle />
          </div>
          <p className="text-xl text-red-600 dark:text-red-400">{error}</p>
          <Link
            to="/"
            className="
              mt-6 px-4 py-2 
              bg-gradient-to-r from-yellow-500 to-yellow-600 
              text-white text-lg rounded-full shadow-md 
              hover:from-yellow-600 hover:to-yellow-700 
              transform hover:-translate-y-1 hover:scale-105 
              transition-all duration-300
            "
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

          <DesktopNavigation
            onHomeClick={() => navigate("/")}
            onBackClick={navigateToChildDepartment}
          />

          {/* Блок с датами и кнопкой «Скачать» */}
          <DateFilterBar
            startDate={startDate}
            endDate={endDate}
            onStartDateChange={handleStartDateChange}
            onEndDateChange={handleEndDateChange}
            onDownload={handleDownload}
            isDownloading={isDownloading}
            isDownloadDisabled={isDownloadDisabled}
            today={today}
          />

          {showWaitMessage && <WaitNotification />}

          <div className="mb-6 px-2 mt-4">
            <SearchInput
              value={searchQuery}
              message="Поиск по ФИО"
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          <p className="text-gray-300 mb-4 px-2 dark:text-gray-400">
            <strong>Количество сотрудников:</strong> {data?.staff_count}
          </p>

          {/* Мобильная версия – карточки */}
          <div className="block md:hidden space-y-2">
            {data?.staff_data &&
              Object.entries(data.staff_data)
                .filter(([, staff]) =>
                  staff.FIO.toLowerCase().includes(searchQuery.toLowerCase())
                )
                .map(([pin, staff]) => (
                  <div
                    key={pin}
                    className="w-fll p-6 rounded-lg sadow-md bg-white dark:bg-gray-800"
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
                      <strong>Должнось: </strong>
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

          {/* Версия для планшетов и ПК – таблица */}
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

          {/* Плавающие кнопки для мобильных устройств */}
          <div className="block md:hidden">
            <FloatingButton
              variant="back"
              icon={<FaArrowLeft size={24} />}
              onClick={navigateToChildDepartment}
              position="left"
            />
            <FloatingButton
              variant="home"
              icon={<FaHome size={24} />}
              to="/"
              position="right"
            />
          </div>
        </>
      )}
    </motion.div>
  );
};

export default ChildDepartmentPage;
