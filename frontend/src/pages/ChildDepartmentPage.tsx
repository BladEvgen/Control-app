import { Link, useNavigate } from "../RouterUtils";
import { useEffect, useState } from "react";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { IChildDepartmentData } from "../schemas/IData";
import { useParams } from "react-router-dom";
import { capitalizeFirstLetter } from "../utils/utils";
import { FaDownload } from "react-icons/fa6";

const ChildDepartmentPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<IChildDepartmentData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [isDownloading, setIsDownloading] = useState<boolean>(false);
  const [showWaitMessage, setShowWaitMessage] = useState<boolean>(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await axiosInstance.get(
          `${apiUrl}/api/child_department/${id}/`
        );
        setData(res.data);
        setIsLoading(false);
      } catch (error) {
        console.error(`Error: ${error}`);
      }
    };

    fetchData();
  }, [id]);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  const navigateToChildDepartment = () => {
    if (data?.child_department.parent) {
      navigate(`/department/${data.child_department.parent}`);
    }
  };

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
    <div className="container mx-auto px-4 py-8">
      {isLoading ? (
        <div className="flex items-center justify-center h-screen">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-gray-900"></div>
        </div>
      ) : (
        <>
          <h1 className="text-3xl font-bold mb-6 text-center md:text-left break-words sm:text-center md:truncate">
            {data?.child_department?.name &&
              capitalizeFirstLetter(data.child_department.name)}
          </h1>
          <button
            onClick={navigateToChildDepartment}
            className="inline-block mb-6 px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 transition-colors duration-300 ease-in-out"
          >
            Вернуться назад
          </button>
          <div className="flex flex-col md:flex-row mb-4">
            <div className="flex flex-col mb-4 md:mr-4">
              <label
                htmlFor="startDate"
                className="block mb-1 font-medium text-gray-700"
              >
                Дата начала:
              </label>
              <input
                type="date"
                id="startDate"
                value={startDate}
                onChange={handleStartDateChange}
                className="border border-gray-300 px-3 py-2 rounded-md w-full md:w-auto "
              />
            </div>
            <div className="flex flex-col mb-4 md:mr-4">
              <label
                htmlFor="endDate"
                className="block mb-1 font-medium text-gray-700"
              >
                Дата конца:
              </label>
              <input
                type="date"
                id="endDate"
                value={endDate}
                onChange={handleEndDateChange}
                className="border border-gray-300 px-3 py-2 rounded-md w-full md:w-auto"
              />
            </div>
            <div className="flex items-center">
              <button
                onClick={handleDownload}
                disabled={isDownloadDisabled || isDownloading}
                className={`flex items-center justify-center w-full md:w-auto px-4 py-2 rounded-md text-white mt-3 ${
                  isDownloadDisabled || isDownloading
                    ? "bg-gray-400 cursor-not-allowed"
                    : "bg-green-500 hover:bg-green-600"
                }`}
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
                <div className="mt-2 md:mt-0 md:ml-4 p-2 bg-red-100 text-red-600 text-sm rounded-lg shadow-md animate-pulse">
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
              className="border border-gray-300 px-4 py-2 rounded-md w-full focus:outline-none focus:border-blue-500 transition-colors duration-300 ease-in-out"
            />
          </div>
          <p className="text-gray-700 mb-4">
            <strong>Количество сотрудников:</strong> {data?.staff_count}
          </p>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-100">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    ФИО
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Должность
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Дата создания
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Avatar
                  </th>
                </tr>
              </thead>
              <tbody>
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
                            className="text-blue-500 hover:underline"
                          >
                            {staff.FIO}
                          </Link>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {staff.positions.length > 2 ? (
                            <>
                              {staff.positions[0]}, ...
                              <span className="text-gray-500 ml-2">
                                (ещё {staff.positions.length - 1})
                              </span>
                            </>
                          ) : (
                            staff.positions.join(", ")
                          )}
                        </td>

                        <td className="px-6 py-4 whitespace-nowrap">
                          {formatDate(staff.date_of_creation)}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {staff.avatar ? (
                            <span role="img" aria-label="success">
                              ✅
                            </span>
                          ) : (
                            <span role="img" aria-label="fail">
                              ❌
                            </span>
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
