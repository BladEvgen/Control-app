import { useState, useEffect } from "react";
import { IData, IChildDepartment } from "../schemas/IData";
import { useParams } from "react-router-dom";
import { Link } from "../RouterUtils";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { capitalizeFirstLetter } from "../utils/utils";
import { FaDownload } from "react-icons/fa6";

const DepartmentTable = ({ data }: { data: IData }) => {
  const [page, setPage] = useState(0);
  const [rowsPerPage] = useState(10);
  const [searchQuery, setSearchQuery] = useState("");

  const handleChangePage = (newPage: number) => {
    setPage(newPage);
  };

  const sortedChildDepartments = [...data.child_departments].sort((a, b) =>
    a.name.localeCompare(b.name)
  );

  const filteredDepartments = sortedChildDepartments.filter((department) =>
    department.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full">
      <input
        type="text"
        placeholder="Поиск отдела"
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        className="border border-gray-300 px-3 py-1 rounded-md mb-4"
      />
      <p className="text-gray-700 mb-4">
        <strong>Количество сотрудников:</strong> {data?.total_staff_count}
      </p>
      <div className="flex-1 overflow-y-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Название отдела
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Дата создания
              </th>
            </tr>
          </thead>
          <tbody>
            {filteredDepartments
              .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
              .map((department: IChildDepartment) => (
                <tr key={department.child_id}>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <Link
                      to={
                        department.has_child_departments
                          ? `/department/${department.child_id}`
                          : `/childDepartment/${department.child_id}`
                      }
                      className="text-sm font-medium text-gray-900 hover:text-indigo-600"
                    >
                      {capitalizeFirstLetter(department.name)}
                    </Link>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {new Date(department.date_of_creation).toLocaleString()}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      <div className="bg-white px-4 py-3 flex items-center justify-between border-t border-gray-200 sm:px-6">
        <div className="flex-1 flex justify-between">
          <div className="flex">
            <button
              onClick={() => handleChangePage(0)}
              disabled={page === 0}
              className="bg-white-500 text-white px-4 py-2 rounded-md text-sm font-medium disabled:opacity-50 mr-2"
            >
              ⏪
            </button>
            <button
              onClick={() => handleChangePage(page - 1)}
              disabled={page === 0}
              className="bg-white-500 text-white px-4 py-2 rounded-md text-sm font-medium disabled:opacity-50 mr-2"
            >
              ◀️
            </button>
          </div>
          <p className="text-sm text-gray-700">
            Показано{" "}
            <span className="font-medium">
              {Math.min((page + 1) * rowsPerPage, filteredDepartments.length)}
            </span>{" "}
            из <span className="font-medium">{filteredDepartments.length}</span>{" "}
            результатов
          </p>
          <div className="flex">
            <button
              onClick={() => handleChangePage(page + 1)}
              disabled={
                page >=
                Math.ceil(sortedChildDepartments.length / rowsPerPage) - 1
              }
              className="bg-white-500 text-white px-4 py-2 rounded-md text-sm font-medium disabled:opacity-50 mr-2"
            >
              ▶️
            </button>
            <button
              onClick={() =>
                handleChangePage(
                  Math.max(
                    0,
                    Math.ceil(sortedChildDepartments.length / rowsPerPage) - 1
                  )
                )
              }
              disabled={
                page >=
                Math.ceil(sortedChildDepartments.length / rowsPerPage) - 1
              }
              className="bg-white-500 text-white px-4 py-2 rounded-md text-sm font-medium disabled:opacity-50"
            >
              ⏩
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

const DepartmentPage = () => {
  const { id } = useParams<{ id: string }>();
  const departmentId = id ? parseInt(id) : 1;
  const [data, setData] = useState<IData>({} as IData);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [showReloadMessage, setShowReloadMessage] = useState<boolean>(false);
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [isDownloading, setIsDownloading] = useState<boolean>(false);
  const [showWaitMessage, setShowWaitMessage] = useState<boolean>(false);
  useEffect(() => {
    const fetchData = async (id: number) => {
      try {
        const res = await axiosInstance.get(`${apiUrl}/api/department/${id}/`);
        setData(res.data);
        setIsLoading(false);

        if (res.status === 200 || res.status === 201) {
          return;
        }

        const timeout1 = setTimeout(() => {
          setShowReloadMessage(true);
        }, 6000);

        const timeout2 = setTimeout(() => {
          window.location.reload();
        }, 10000);

        return () => {
          clearTimeout(timeout1);
          clearTimeout(timeout2);
        };
      } catch (error) {
        console.error(`Error: ${error}`);
      }
    };

    fetchData(departmentId);
  }, [departmentId]);

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
      }, 5000);
      return () => clearTimeout(hideWaitMessage);
    }, 3000);

    try {
      const response = await axiosInstance.get(
        `${apiUrl}/api/download/${id ?? departmentId}/`,
        {
          params: {
            startDate,
            endDate,
          },
          responseType: "blob",
        }
      );

      clearTimeout(downloadTimeout);
      setIsDownloading(false);
      const departmentName = data.name.replace(/\s/g, "_");

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
      <h1 className="text-2xl font-bold mb-4">
        {isLoading ? "Loading..." : data?.name}
      </h1>
      {location.pathname !== "/app/" && (
        <Link
          to="/"
          className="inline-block mb-4 px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600"
        >
          Вернуться на главную страницу
        </Link>
      )}
      <div className="flex flex-col md:flex-row items-center mb-6 space-y-4 md:space-y-0 md:space-x-4">
        <div className="flex flex-col">
          <label htmlFor="startDate" className="text-sm text-gray-600">
            Начальная дата
          </label>
          <div className="relative">
            <input
              type="date"
              id="startDate"
              value={startDate}
              onChange={handleStartDateChange}
              className="border border-gray-300 px-4 py-2 rounded-md focus:outline-none focus:border-blue-500 transition-colors duration-300 ease-in-out"
            />
          </div>
        </div>
        <div className="flex flex-col">
          <label htmlFor="endDate" className="text-sm text-gray-600">
            Конечная дата
          </label>
          <div className="relative">
            <input
              type="date"
              id="endDate"
              value={endDate}
              onChange={handleEndDateChange}
              className="border border-gray-300 px-4 py-2 rounded-md focus:outline-none focus:border-blue-500 transition-colors duration-300 ease-in-out"
            />
          </div>
        </div>
        <div className="flex items-center">
          <button
            onClick={handleDownload}
            disabled={isDownloadDisabled || isDownloading}
            className={`px-4 py-2 mt-5 ${
              isDownloadDisabled || isDownloading
                ? "bg-gray-300 cursor-not-allowed"
                : "bg-green-500 hover:bg-green-600"
            } text-white rounded-md flex items-center transition-colors duration-300 ease-in-out`}
          >
            <FaDownload className="mr-2" />
            Скачать
          </button>
          {showWaitMessage && (
            <p className="text-gray-500 text-sm mt-4 px-4 py-2 bg-yellow-100 border border-yellow-400 rounded-md ml-4">
              Подождите, загрузка может занять некоторое время...
            </p>
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-white z-50">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-gray-900"></div>
          {showReloadMessage && (
            <p className="text-gray-500 text-sm mt-2">
              Попробуйте перезагрузить страницу
            </p>
          )}
        </div>
      ) : (
        <DepartmentTable data={data} />
      )}
    </div>
  );
};

export default DepartmentPage;
