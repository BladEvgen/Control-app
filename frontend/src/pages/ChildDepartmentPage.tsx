import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { IChildDepartmentData } from "../schemas/IData";
import { useParams } from "react-router-dom";

const ChildDepartmentPage = () => {
  const { id } = useParams<{ id: string }>();
  const [showReloadMessage, setShowReloadMessage] = useState<boolean>(false);
  const [data, setData] = useState<IChildDepartmentData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

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

  return (
    <div className="m-8">
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
        <>
          <h1 className="text-2xl font-bold mb-4">
            {data?.child_department.name}
          </h1>
          <Link
            to="/"
            className="inline-block mb-4 px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600">
            На главную страницу
          </Link>
          <p>Количество сотрудников: {data?.staff_count}</p>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
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
                  Object.entries(data?.staff_data).map(([pin, staff]) => (
                    <tr key={pin}>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <Link to={`/staffDetail/${pin}`}>{staff.FIO}</Link>
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
