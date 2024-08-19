import { useState, useEffect, ChangeEvent } from "react";
import { IData } from "../schemas/IData";
import { useParams, useLocation } from "react-router-dom";
import { Link } from "../RouterUtils";

import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { formatDepartmentName } from "../utils/utils";
import { FaDownload, FaHome, FaTimesCircle } from "react-icons/fa";
import DepartmentTable from "./DepartmentTable";
import { BaseAction } from "../schemas/BaseAction";

class DepartmentAction extends BaseAction<any> {
  static SET_LOADING = "SET_LOADING";
  static SET_DATA = "SET_DATA";
  static SET_ERROR = "SET_ERROR";
}

const shouldRenderLink = (pathname: string): boolean => {
  const excludedPaths = ["/app/", "/app/department/1", "/app"];
  return !excludedPaths.includes(pathname);
};

const formatDate = (date: Date, offsetDays: number): string => {
  return new Date(new Date().setDate(date.getDate() + offsetDays))
    .toISOString()
    .split("T")[0];
};

const fetchDepartmentData = async (
  id: number,
  dispatch: React.Dispatch<DepartmentAction>
): Promise<void> => {
  dispatch(new DepartmentAction(DepartmentAction.SET_LOADING, true));

  try {
    const res = await axiosInstance.get(`${apiUrl}/api/department/${id}/`);
    dispatch(new DepartmentAction(DepartmentAction.SET_DATA, res.data));
  } catch (error) {
    console.error(`Error: ${error}`);
    dispatch(
      new DepartmentAction(
        DepartmentAction.SET_ERROR,
        "Не удалось загрузить данные"
      )
    );
  }
};

const handleFileDownload = async (
  url: string,
  startDate: string,
  endDate: string,
  data: IData,
  setIsDownloading: React.Dispatch<React.SetStateAction<boolean>>,
  setShowWaitMessage: React.Dispatch<React.SetStateAction<boolean>>
): Promise<void> => {
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
    const response = await axiosInstance.get(url, {
      params: { startDate, endDate },
      responseType: "blob",
      timeout: 600000,
    });

    clearTimeout(downloadTimeout);
    setIsDownloading(false);
    const departmentName = data.name.replace(/\s/g, "_");

    const fileUrl = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement("a");
    link.href = fileUrl;
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

const DepartmentPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const departmentId = id ? parseInt(id) : 1;
  const [data, setData] = useState<IData>({
    name: "",
    date_of_creation: "",
    child_departments: [],
    total_staff_count: 0,
  });
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState<string>(
    formatDate(new Date(), -31)
  );
  const [endDate, setEndDate] = useState<string>(formatDate(new Date(), 0));
  const [isDownloading, setIsDownloading] = useState<boolean>(false);
  const [showWaitMessage, setShowWaitMessage] = useState<boolean>(false);

  const dispatch = (action: DepartmentAction) => {
    switch (action.type) {
      case DepartmentAction.SET_LOADING:
        setIsLoading(action.payload as boolean);
        break;
      case DepartmentAction.SET_DATA:
        setData(action.payload as IData);
        setIsLoading(false);
        break;
      case DepartmentAction.SET_ERROR:
        setError(action.payload as string);
        setIsLoading(false);
        break;
    }
  };

  useEffect(() => {
    fetchDepartmentData(departmentId, dispatch);
  }, [departmentId]);

  const handleDateChange = (
    e: ChangeEvent<HTMLInputElement>,
    setDate: React.Dispatch<React.SetStateAction<string>>,
    otherDate: string,
    compare: (newDate: string, otherDate: string) => boolean
  ) => {
    const newDate = e.target.value;
    setDate(newDate);
    if (compare(newDate, otherDate)) {
      setEndDate(newDate);
    }
  };

  const handleDownload = () => {
    handleFileDownload(
      `${apiUrl}/api/download/${departmentId}/`,
      startDate,
      endDate,
      data,
      setIsDownloading,
      setShowWaitMessage
    );
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
            {formatDepartmentName(data?.name)}
          </h1>

          <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-6">
            {shouldRenderLink(location.pathname) && (
              <Link
                to="/"
                className="flex items-center justify-center px-3 py-2 bg-yellow-500 text-white text-lg rounded-lg shadow-md hover:bg-yellow-600 dark:bg-yellow-700 dark:hover:bg-yellow-800 transition-colors duration-300 ease-in-out mb-4 md:mb-0"
              >
                <FaHome className="mr-2" />
                <span className="font-semibold">На главную</span>
              </Link>
            )}
          </div>

          <div className="flex flex-col md:flex-row md:space-x-4 mb-6">
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
                onChange={(e) =>
                  handleDateChange(
                    e,
                    setStartDate,
                    endDate,
                    (newDate, otherDate) => newDate > otherDate
                  )
                }
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
                onChange={(e) =>
                  handleDateChange(
                    e,
                    setEndDate,
                    startDate,
                    (newDate, otherDate) => newDate >= otherDate
                  )
                }
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

          {data && <DepartmentTable data={data} />}
        </>
      )}
    </div>
  );
};

export default DepartmentPage;
