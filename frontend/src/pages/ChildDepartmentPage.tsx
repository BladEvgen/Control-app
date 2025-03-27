import { Link, useNavigate } from "../RouterUtils";
import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { IChildDepartmentData } from "../schemas/IData";
import { formatDepartmentName } from "../utils/utils";
import {
  FaUserCheck,
  FaUserTimes,
  FaArrowLeft,
  FaHome,
  FaBuilding,
  FaUsers,
} from "react-icons/fa";
import { motion, AnimatePresence } from "framer-motion";
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
          new BaseAction(
            BaseAction.SET_ERROR,
            "Не удалось загрузить данные. Пожалуйста, попробуйте еще раз."
          )
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

  const filteredStaff = data?.staff_data
    ? Object.entries(data.staff_data).filter(([, staff]) =>
        staff.FIO.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : [];

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.2,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 },
  };

  return (
    <AnimatePresence mode="wait">
      <motion.div
        className="max-w-7xl mx-auto pb-10"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        exit={{ opacity: 0 }}
      >
        {isLoading ? (
          <LoaderComponent />
        ) : error ? (
          <motion.div
            className="flex flex-col items-center justify-center min-h-[50vh] p-6 card text-center"
            variants={itemVariants}
          >
            <div className="text-red-500 text-5xl mb-6">
              <FaUserTimes />
            </div>
            <h2 className="text-2xl font-bold text-red-600 dark:text-red-400 mb-4">
              {error}
            </h2>
            <Link to="/" className="btn-primary mt-4">
              Вернуться на главную
            </Link>
          </motion.div>
        ) : (
          <>
            <motion.div
              className="mb-8 flex items-center"
              variants={itemVariants}
            >
              <FaBuilding className="text-primary-600 dark:text-primary-400 mr-3 text-2xl md:text-3xl" />
              <h1 className="section-title mb-0">
                {data?.child_department?.name &&
                  formatDepartmentName(data.child_department.name)}
              </h1>
            </motion.div>

            <motion.div variants={itemVariants}>
              <DesktopNavigation
                onHomeClick={() => navigate("/")}
                onBackClick={navigateToChildDepartment}
              />
            </motion.div>

            <motion.div variants={itemVariants} className="mt-6 mb-6">
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
            </motion.div>

            {showWaitMessage && (
              <motion.div
                variants={itemVariants}
                className="mx-auto max-w-3xl my-4"
              >
                <WaitNotification />
              </motion.div>
            )}

            <motion.div variants={itemVariants} className="mb-6 card p-5">
              <div className="flex flex-col md:flex-row md:items-center gap-4">
                <div className="flex-1">
                  <div className="flex items-center mb-2">
                    <FaUsers className="text-lg text-primary-600 dark:text-primary-400 mr-2" />
                    <h3 className="font-medium text-lg">
                      Информация о сотрудниках
                    </h3>
                  </div>
                  <p className="text-gray-600 dark:text-gray-400">
                    <strong>Всего сотрудников:</strong>{" "}
                    <span className="font-semibold text-primary-700 dark:text-primary-300">
                      {data?.staff_count}
                    </span>
                  </p>
                </div>
                <div className="w-full md:w-1/3">
                  <SearchInput
                    value={searchQuery}
                    message="Поиск по ФИО"
                    onChange={(e) => setSearchQuery(e.target.value)}
                  />
                </div>
              </div>
            </motion.div>

            {/* Mobile cards view */}
            <motion.div
              className="block md:hidden space-y-4"
              variants={containerVariants}
            >
              {filteredStaff.length === 0 ? (
                <motion.div
                  variants={itemVariants}
                  className="text-center p-8 text-gray-500"
                >
                  Сотрудники не найдены
                </motion.div>
              ) : (
                filteredStaff.map(([pin, staff]) => (
                  <motion.div
                    key={pin}
                    variants={itemVariants}
                    whileHover={{ scale: 1.02 }}
                    transition={{ duration: 0.2 }}
                    className="card p-5"
                  >
                    <div className="flex justify-between items-start">
                      <Link
                        to={`/staffDetail/${pin}`}
                        className="text-primary-700 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300 font-semibold text-lg transition-colors"
                      >
                        {staff.FIO}
                      </Link>
                      <div className="p-1">
                        {staff.avatar ? (
                          <FaUserCheck
                            className="text-success-500 text-xl"
                            aria-label="Верифицирован"
                          />
                        ) : (
                          <FaUserTimes
                            className="text-danger-500 text-xl"
                            aria-label="Не верифицирован"
                          />
                        )}
                      </div>
                    </div>
                    <div className="mt-3">
                      <div className="flex flex-col space-y-2">
                        <div>
                          <span className="text-gray-600 dark:text-gray-400 font-medium">
                            Должность:
                          </span>{" "}
                          <span className="text-gray-800 dark:text-gray-200">
                            {staff.positions.length > 2
                              ? `${staff.positions[0]}, ... (ещё ${
                                  staff.positions.length - 1
                                })`
                              : staff.positions.join(", ")}
                          </span>
                        </div>
                        <div>
                          <span className="text-gray-600 dark:text-gray-400 font-medium">
                            Дата создания:
                          </span>{" "}
                          <span className="text-gray-800 dark:text-gray-200">
                            {new Date(
                              staff.date_of_creation
                            ).toLocaleDateString()}
                          </span>
                        </div>
                      </div>
                    </div>
                  </motion.div>
                ))
              )}
            </motion.div>

            {/* Desktop table view */}
            <motion.div
              variants={itemVariants}
              className="hidden md:block card overflow-hidden"
            >
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-800">
                  <tr>
                    <th
                      scope="col"
                      className="px-6 py-3.5 text-left text-sm font-semibold text-primary-900 dark:text-primary-100 uppercase tracking-wider"
                    >
                      ФИО
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3.5 text-left text-sm font-semibold text-primary-900 dark:text-primary-100 uppercase tracking-wider"
                    >
                      Должность
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3.5 text-left text-sm font-semibold text-primary-900 dark:text-primary-100 uppercase tracking-wider"
                    >
                      Дата создания
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3.5 text-left text-sm font-semibold text-primary-900 dark:text-primary-100 uppercase tracking-wider"
                    >
                      Статус
                    </th>
                    <th scope="col" className="relative px-6 py-3.5">
                      <span className="sr-only">Просмотр</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-800">
                  {filteredStaff.length === 0 ? (
                    <tr>
                      <td
                        colSpan={5}
                        className="px-6 py-8 text-center text-gray-500 dark:text-gray-400"
                      >
                        Сотрудники не найдены
                      </td>
                    </tr>
                  ) : (
                    filteredStaff.map(([pin, staff]) => (
                      <tr
                        key={pin}
                        className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors duration-150"
                      >
                        <td className="px-6 py-4 whitespace-nowrap">
                          <Link
                            to={`/staffDetail/${pin}`}
                            className="text-primary-700 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300 font-medium transition-colors"
                          >
                            {staff.FIO}
                          </Link>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {staff.positions.length > 2 ? (
                            <span className="inline-flex items-center">
                              {staff.positions[0]}{" "}
                              <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300">
                                +{staff.positions.length - 1}
                              </span>
                            </span>
                          ) : (
                            staff.positions.join(", ")
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400 font-mono">
                          {new Date(
                            staff.date_of_creation
                          ).toLocaleDateString()}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {staff.avatar ? (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                              <FaUserCheck className="mr-1" /> Верифицирован
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400">
                              <FaUserTimes className="mr-1" /> Не верифицирован
                            </span>
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                          <Link
                            to={`/staffDetail/${pin}`}
                            className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-lg bg-primary-100 text-primary-700 hover:bg-primary-200 dark:bg-primary-900/30 dark:text-primary-400 dark:hover:bg-primary-800/50"
                          >
                            Показать детали
                          </Link>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </motion.div>
          </>
        )}
      </motion.div>

      {/* Floating buttons for mobile */}
      {!isLoading && !error && (
        <div className="block md:hidden">
          <FloatingButton
            variant="back"
            icon={<FaArrowLeft size={20} />}
            onClick={navigateToChildDepartment}
            position="left"
          />
          <FloatingButton
            variant="home"
            icon={<FaHome size={20} />}
            to="/"
            position="right"
          />
        </div>
      )}
    </AnimatePresence>
  );
};

export default ChildDepartmentPage;
