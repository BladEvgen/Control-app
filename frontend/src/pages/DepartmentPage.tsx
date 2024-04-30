import { useState, useEffect } from "react";
import { IData, IChildDepartment } from "../schemas/IData";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { Link, useParams } from "react-router-dom";

const DepartmentTable = ({ data }: { data: IData }) => {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(5);

  const handleChangePage = (newPage: number) => {
    setPage(newPage);
  };

  const sortedChildDepartments = [...data.child_departments].sort((a, b) =>
    a.name.localeCompare(b.name)
  );

  return (
    <>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Имя пототдела
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Дата создания
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedChildDepartments
              .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
              .map((department: IChildDepartment) => (
                <tr key={department.child_id}>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <Link
                      to={`/childDepartment/${department.child_id}`}
                      className="text-sm font-medium text-gray-900 hover:text-indigo-600">
                      {department.name}
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
        <div className="flex-1 flex justify-between sm:hidden">
          <button
            onClick={() => handleChangePage(page - 1)}
            disabled={page === 0}
            className="bg-white px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-500 hover:bg-gray-50">
            Назад
          </button>
          <button
            onClick={() => handleChangePage(page + 1)}
            disabled={
              page >= Math.ceil(sortedChildDepartments.length / rowsPerPage) - 1
            }
            className="bg-white px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-500 hover:bg-gray-50">
            Вперед
          </button>
        </div>
        <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
          <div>
            <p className="text-sm text-gray-700">
              Показано{" "}
              <span className="font-medium">
                {Math.min(
                  (page + 1) * rowsPerPage,
                  sortedChildDepartments.length
                )}
              </span>{" "}
              из{" "}
              <span className="font-medium">
                {sortedChildDepartments.length}
              </span>{" "}
              результатов
            </p>
          </div>
          <div>
            <nav
              className="relative z-0 inline-flex rounded-md shadow-sm -space-x-px"
              aria-label="Pagination">
              <button
                onClick={() => handleChangePage(0)}
                disabled={page === 0}
                className="bg-white border border-gray-300 rounded-l-md px-3 py-2 inline-flex items-center text-sm font-medium text-gray-500 hover:bg-gray-50">
                Первая
              </button>
              <button
                onClick={() => handleChangePage(page - 1)}
                disabled={page === 0}
                className="bg-white border border-gray-300 rounded-l-md px-3 py-2 inline-flex items-center text-sm font-medium text-gray-500 hover:bg-gray-50">
                Назад
              </button>
              <button
                onClick={() => handleChangePage(page + 1)}
                disabled={
                  page >=
                  Math.ceil(sortedChildDepartments.length / rowsPerPage) - 1
                }
                className="bg-white border border-gray-300 px-3 py-2 inline-flex items-center text-sm font-medium text-gray-500 hover:bg-gray-50">
                Вперед
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
                className="bg-white border border-gray-300 rounded-r-md px-3 py-2 inline-flex items-center text-sm font-medium text-gray-500 hover:bg-gray-50">
                Последняя
              </button>
            </nav>
          </div>
        </div>
      </div>
    </>
  );
};

const DepartmentPage = () => {
  const { id } = useParams<{ id: string }>();
  const departmentId = id ? parseInt(id) : 4958;
  const [data, setData] = useState<IData>({} as IData);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [showReloadMessage, setShowReloadMessage] = useState<boolean>(false);

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
        }, 15000);

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

  return (
    <div className="m-8">
      <h1 className="text-2xl font-bold mb-4">
        {isLoading ? "Loading..." : data?.name}
      </h1>
      <Link
        to="/"
        className="inline-block mb-4 px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600">
        На главный отдел
      </Link>
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
