import { Link, useNavigate } from "../RouterUtils";
import { useEffect, useState } from "react";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { IChildDepartmentData } from "../schemas/IData";
import { useParams } from "react-router-dom";
import { capitalizeFirstLetter } from "../utils/utils";

const ChildDepartmentPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [showReloadMessage, setShowReloadMessage] = useState<boolean>(false);
  const [data, setData] = useState<IChildDepartmentData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [searchQuery, setSearchQuery] = useState<string>("");

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await axiosInstance.get(
          `${apiUrl}/api/child_department/${id}/`
        );
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

  return (
    <div className="container mx-auto px-4 py-8">
      {isLoading ? (
        <div className="flex items-center justify-center h-screen">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-gray-900"></div>
          {showReloadMessage && (
            <p className="text-gray-500 text-sm ml-2">
              Попробуйте перезагрузить страницу
            </p>
          )}
        </div>
      ) : (
        <>
          <h1 className="text-3xl font-bold mb-6">
            {data?.child_department?.name &&
              capitalizeFirstLetter(data.child_department.name)}
          </h1>
          <button
            onClick={navigateToChildDepartment}
            className="inline-block mb-6 px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 transition-colors duration-300 ease-in-out"
          >
            Вернуться назад
          </button>

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
                          {staff.positions.join(", ")}
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
