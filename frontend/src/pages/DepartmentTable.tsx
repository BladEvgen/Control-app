import { useState, ChangeEvent } from "react";
import { IData } from "../schemas/IData";
import { Link } from "../RouterUtils";
import { formatDepartmentName } from "../utils/utils";
import {
  FaChevronLeft,
  FaChevronRight,
  FaAngleDoubleLeft,
  FaAngleDoubleRight,
} from "react-icons/fa";

interface DepartmentTableProps {
  data: IData;
}

const DepartmentTable: React.FC<DepartmentTableProps> = ({ data }) => {
  const [page, setPage] = useState<number>(0);
  const [rowsPerPage] = useState<number>(10);
  const [searchQuery, setSearchQuery] = useState<string>("");

  const sortedChildDepartments = (data.child_departments || []).sort((a, b) =>
    a.name.localeCompare(b.name)
  );

  const filteredDepartments = sortedChildDepartments.filter((department) =>
    department.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleChangePage = (newPage: number) => {
    setPage(newPage);
  };

  const handleSearchChange = (e: ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value);
    setPage(0);
  };

  const renderPaginationButton = (
    onClick: () => void,
    disabled: boolean,
    icon: React.ReactNode,
    additionalClasses: string = ""
  ) => (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-4 py-2 rounded-md text-sm font-medium ${additionalClasses} ${
        disabled
          ? "text-gray-300 dark:text-gray-600"
          : "text-gray-700 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200"
      }`}
    >
      {icon}
    </button>
  );

  return (
    <div className="flex flex-col h-full rounded-lg shadow-lg">
      <input
        type="text"
        placeholder="Поиск отдела"
        value={searchQuery}
        onChange={handleSearchChange}
        className="border border-gray-300 px-4 py-2 rounded-md mb-4 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:text-white dark:border-gray-600"
      />
      <p className="text mb-4 ml-3 text-gray-300 dark:text-gray-400">
        <strong>Количество сотрудников:</strong> {data.total_staff_count}
      </p>

      {/* Для мобильных устройств */}
      <div className="block md:hidden space-y-4">
        {filteredDepartments
          .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
          .map((department) => (
            <div
              key={department.child_id}
              className="p-4 bg-white dark:bg-gray-800 rounded-lg shadow-md"
            >
              <Link
                to={
                  department.has_child_departments
                    ? `/department/${department.child_id}`
                    : `/childDepartment/${department.child_id}`
                }
                className="text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-600 font-semibold text-lg"
              >
                {formatDepartmentName(department.name)}
              </Link>
              <p className="text-gray-600 dark:text-gray-400">
                <strong>Дата создания: </strong>
                {new Date(department.date_of_creation).toLocaleString()}
              </p>
            </div>
          ))}
      </div>

      {/* Для планшетов и ПК */}
      <div className="hidden md:block flex-1 overflow-y-auto">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400">
                Название отдела
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400">
                Дата создания
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200 dark:bg-gray-900 dark:divide-gray-700">
            {filteredDepartments
              .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
              .map((department) => (
                <tr key={department.child_id}>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <Link
                      to={
                        department.has_child_departments
                          ? `/department/${department.child_id}`
                          : `/childDepartment/${department.child_id}`
                      }
                      className="text-sm font-medium text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-600"
                    >
                      {formatDepartmentName(department.name)}
                    </Link>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                    {new Date(department.date_of_creation).toLocaleString()}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      <div className="bg-white px-4 py-3 flex items-center justify-between border-t border-gray-200 sm:px-6 rounded-b-lg dark:bg-gray-800 dark:border-gray-700">
        <div className="flex-1 flex justify-between">
          <div className="flex">
            {renderPaginationButton(
              () => handleChangePage(0),
              page === 0,
              <FaAngleDoubleLeft size={16} />
            )}
            {renderPaginationButton(
              () => handleChangePage(page - 1),
              page === 0,
              <FaChevronLeft size={16} />
            )}
          </div>
          <p className="text-sm text-gray-700 dark:text-gray-400">
            Показано{" "}
            <span className="font-medium">
              {Math.min((page + 1) * rowsPerPage, filteredDepartments.length)}
            </span>{" "}
            из <span className="font-medium">{filteredDepartments.length}</span>{" "}
            результатов
          </p>
          <div className="flex">
            {renderPaginationButton(
              () => handleChangePage(page + 1),
              page >= Math.ceil(filteredDepartments.length / rowsPerPage) - 1,
              <FaChevronRight size={16} />
            )}
            {renderPaginationButton(
              () =>
                handleChangePage(
                  Math.max(
                    0,
                    Math.ceil(filteredDepartments.length / rowsPerPage) - 1
                  )
                ),
              page >= Math.ceil(filteredDepartments.length / rowsPerPage) - 1,
              <FaAngleDoubleRight size={16} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default DepartmentTable;
