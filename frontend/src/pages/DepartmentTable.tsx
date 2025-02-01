import { useState, ChangeEvent } from "react";
import { IData } from "../schemas/IData";
import { Link } from "../RouterUtils";
import { formatDepartmentName } from "../utils/utils";
import { motion } from "framer-motion";
import {
  FaChevronLeft,
  FaChevronRight,
  FaAngleDoubleLeft,
  FaAngleDoubleRight,
} from "react-icons/fa";

interface DepartmentTableProps {
  data: IData;
}

const itemVariants = {
  hidden: { opacity: 0, scale: 0.95 },
  visible: { opacity: 1, scale: 1 },
};

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

  const totalPages = Math.ceil(filteredDepartments.length / rowsPerPage);

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
    <motion.button
      onClick={onClick}
      disabled={disabled}
      whileHover={{ scale: disabled ? 1 : 1.05 }}
      className={`px-3 py-1 rounded-md text-sm font-medium transition-colors duration-150 ${additionalClasses} ${
        disabled
          ? "text-gray-300 dark:text-gray-600"
          : "text-gray-700 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200"
      }`}
    >
      {icon}
    </motion.button>
  );

  const renderPageNumber = (pageNumber: number) => (
    <motion.button
      key={pageNumber}
      onClick={() => handleChangePage(pageNumber)}
      whileHover={{ scale: 1.05 }}
      className={`px-3 py-1 border rounded-md text-sm font-medium transition-colors duration-150 ${
        page === pageNumber
          ? "bg-blue-600 text-white border-blue-600 shadow-md"
          : "bg-white text-gray-700 border-gray-300 hover:bg-gray-100"
      } dark:shadow-none dark:hover:bg-gray-600 ${
        page === pageNumber
          ? "dark:bg-blue-500 dark:text-white dark:border-blue-500"
          : "dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600"
      }`}
    >
      {pageNumber + 1}
    </motion.button>
  );

  const visiblePages: number[] = [];
  if (totalPages > 0) {
    if (page > 0) {
      visiblePages.push(page - 1);
    }
    visiblePages.push(page);
    if (page < totalPages - 1) {
      visiblePages.push(page + 1);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
      className="flex flex-col h-full rounded-lg shadow-lg"
    >
      <motion.input
        type="text"
        placeholder="Поиск отдела"
        value={searchQuery}
        onChange={handleSearchChange}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3 }}
        className="border border-gray-300 px-4 py-2 rounded-md mb-4 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:text-white dark:border-gray-600"
      />
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3, delay: 0.1 }}
        className="mb-4 ml-3 text-gray-700 dark:text-gray-300"
      >
        <strong>Количество сотрудников:</strong> {data.total_staff_count}
      </motion.p>

      {/* Отображение для мобильных устройств */}
      <div className="block md:hidden space-y-4">
        {filteredDepartments
          .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
          .map((department, index) => (
            <motion.div
              key={department.child_id}
              variants={itemVariants}
              initial="hidden"
              animate="visible"
              transition={{ duration: 0.3, delay: index * 0.05 }}
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
            </motion.div>
          ))}
      </div>

      {/* Отображение для планшетов и ПК */}
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
              .map((department, index) => (
                <motion.tr
                  key={department.child_id}
                  variants={itemVariants}
                  initial="hidden"
                  animate="visible"
                  transition={{ duration: 0.3, delay: index * 0.05 }}
                >
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
                </motion.tr>
              ))}
          </tbody>
        </table>
      </div>

      <div className="bg-gray-50 px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between border-t border-gray-200 rounded-b-lg dark:bg-gray-800 dark:border-gray-700">
        <div className="text-sm text-gray-700 dark:text-gray-300 mb-2 sm:mb-0">
          Показано{" "}
          <span className="font-medium">
            {Math.min((page + 1) * rowsPerPage, filteredDepartments.length)}
          </span>{" "}
          из <span className="font-medium">{filteredDepartments.length}</span>{" "}
          результатов
        </div>
        <div className="flex items-center space-x-2">
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
          {visiblePages.map((p) => renderPageNumber(p))}
          {renderPaginationButton(
            () => handleChangePage(page + 1),
            page >= totalPages - 1,
            <FaChevronRight size={16} />
          )}
          {renderPaginationButton(
            () => handleChangePage(totalPages - 1),
            page >= totalPages - 1,
            <FaAngleDoubleRight size={16} />
          )}
        </div>
      </div>
    </motion.div>
  );
};

export default DepartmentTable;
