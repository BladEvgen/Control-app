import { useState, ChangeEvent, useMemo } from "react";
import { IData } from "../schemas/IData";
import { Link } from "../RouterUtils";
import { formatDepartmentName } from "../utils/utils";
import { motion } from "framer-motion";
import SearchInput from "../components/SearchInput";
import {
  FaChevronLeft,
  FaChevronRight,
  FaAngleDoubleLeft,
  FaAngleDoubleRight,
  FaCalendarAlt,
  FaFolder,
  FaFolderOpen,
} from "react-icons/fa";

interface DepartmentTableProps {
  data: IData;
  mode?: "root" | "department";
}

const DepartmentTable: React.FC<DepartmentTableProps> = ({
  data,
  mode = "department",
}) => {
  const [page, setPage] = useState<number>(0);
  const [rowsPerPage] = useState<number>(10);
  const [searchQuery, setSearchQuery] = useState<string>("");

  const filteredDepartments = useMemo(() => {
    return (data?.child_departments ?? [])
      .sort((a, b) => a.name.localeCompare(b.name))
      .filter((department) =>
        department.name.toLowerCase().includes(searchQuery.toLowerCase())
      );
  }, [data, searchQuery]);

  const totalPages = Math.ceil(filteredDepartments.length / rowsPerPage);
  const visibleDepartments = filteredDepartments.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  const handleChangePage = (newPage: number) => {
    setPage(newPage);
  };

  const handleSearchChange = (e: ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value);
    setPage(0);
  };

  const visiblePages = useMemo(() => {
    const pages: number[] = [];
    const maxButtons = 5;

    if (totalPages <= maxButtons) {
      for (let i = 0; i < totalPages; i++) {
        pages.push(i);
      }
    } else {
      pages.push(0);

      const startPage = Math.max(1, page - 1);
      const endPage = Math.min(totalPages - 2, page + 1);

      if (startPage > 1) {
        pages.push(-1);
      }

      for (let i = startPage; i <= endPage; i++) {
        pages.push(i);
      }

      if (endPage < totalPages - 2) {
        pages.push(-2);
      }

      pages.push(totalPages - 1);
    }

    return pages;
  }, [totalPages, page]);

  const tableVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.05,
        delayChildren: 0.1,
      },
    },
  };

  const rowVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.3 },
    },
  };

  const cardVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.3 },
    },
    hover: {
      y: -5,
      boxShadow:
        "0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
    },
  };

  return (
    <div className="flex flex-col">
      <div className="p-6">
        <div className="mb-6">
          <SearchInput
            value={searchQuery}
            onChange={handleSearchChange}
            message="Поиск отдела"
          />
        </div>

        <div className="flex flex-wrap gap-2 mb-6">
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.2 }}
            className="inline-flex items-center px-4 py-2 bg-primary-50 dark:bg-primary-900/30 text-primary-800 dark:text-primary-200 rounded-full"
          >
            <FaFolder className="mr-2 text-primary-600 dark:text-primary-400" />
            <span className="font-medium">Всего сотрудников: </span>
            <span className="ml-1 font-medium text-primary-700 dark:text-primary-300">
              {data.total_staff_count}
            </span>
          </motion.div>
        </div>

        {/* Mobile card view */}
        <motion.div
          className="block md:hidden space-y-4"
          variants={tableVariants}
          initial="hidden"
          animate="visible"
        >
          {visibleDepartments.length === 0 ? (
            <motion.div
              variants={rowVariants}
              className="text-center p-6 text-gray-500 dark:text-gray-400"
            >
              Отделы не найдены
            </motion.div>
          ) : (
            visibleDepartments.map((department) => (
              <motion.div
                key={department.child_id}
                variants={cardVariants}
                whileHover="hover"
                className="card p-5"
              >
                <Link
                  to={
                    mode === "root"
                      ? `/department/${department.child_id}`
                      : `/childDepartment/${department.child_id}`
                  }
                  className="block"
                >
                  <div className="flex items-start mb-3">
                    <FaFolderOpen className="text-primary-500 dark:text-primary-400 text-xl mt-1 mr-3" />
                    <h3 className="text-lg font-medium text-primary-700 dark:text-primary-300">
                      {formatDepartmentName(department.name)}
                    </h3>
                  </div>
                  <div className="flex items-center text-sm text-gray-600 dark:text-gray-400 ml-8">
                    <FaCalendarAlt className="mr-2 text-gray-500 dark:text-gray-500" />
                    <span className="font-mono">
                      {new Date(
                        department.date_of_creation
                      ).toLocaleDateString()}
                    </span>
                  </div>
                </Link>
              </motion.div>
            ))
          )}
        </motion.div>

        {/* Desktop table view */}
        <motion.div
          className="hidden md:block overflow-hidden rounded-lg"
          variants={tableVariants}
          initial="hidden"
          animate="visible"
        >
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th
                  scope="col"
                  className="py-3.5 pl-6 pr-3 text-left text-sm font-semibold text-primary-900 dark:text-primary-100 uppercase tracking-wider"
                >
                  Название отдела
                </th>
                <th
                  scope="col"
                  className="py-3.5 px-3 text-left text-sm font-semibold text-primary-900 dark:text-primary-100 uppercase tracking-wider"
                >
                  Дата создания
                </th>
                <th scope="col" className="relative py-3.5 pl-3 pr-6">
                  <span className="sr-only">Действия</span>
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200 dark:bg-gray-800 dark:divide-gray-700">
              {visibleDepartments.length === 0 ? (
                <tr>
                  <td
                    colSpan={3}
                    className="px-6 py-4 text-center text-gray-500 dark:text-gray-400"
                  >
                    Отделы не найдены
                  </td>
                </tr>
              ) : (
                visibleDepartments.map((department) => (
                  <motion.tr
                    key={department.child_id}
                    variants={rowVariants}
                    className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors duration-200"
                  >
                    <td className="py-4 pl-6 pr-3 whitespace-nowrap">
                      <div className="flex items-center">
                        <FaFolderOpen className="flex-shrink-0 h-5 w-5 text-primary-500 dark:text-primary-400 mr-3" />
                        <Link
                          to={
                            department.has_child_departments
                              ? `/department/${department.child_id}`
                              : `/childDepartment/${department.child_id}`
                          }
                          className="text-base font-medium text-primary-700 hover:text-primary-900 dark:text-primary-300 dark:hover:text-primary-100 transition-colors duration-200"
                        >
                          {formatDepartmentName(department.name)}
                        </Link>
                      </div>
                    </td>
                    <td className="px-3 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400 font-mono">
                      {new Date(
                        department.date_of_creation
                      ).toLocaleDateString()}
                    </td>
                    <td className="py-4 pl-3 pr-6 whitespace-nowrap text-right text-sm">
                      <Link
                        to={
                          department.has_child_departments
                            ? `/department/${department.child_id}`
                            : `/childDepartment/${department.child_id}`
                        }
                        className="inline-flex items-center px-2.5 py-1.5 border border-transparent text-xs font-medium rounded-full bg-primary-100 text-primary-700 hover:bg-primary-200 dark:bg-primary-900/30 dark:text-primary-300 dark:hover:bg-primary-800/50 transition-colors duration-200"
                      >
                        Показать
                      </Link>
                    </td>
                  </motion.tr>
                ))
              )}
            </tbody>
          </table>
        </motion.div>

        {totalPages > 1 && (
          <div className="mt-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="text-sm text-gray-700 dark:text-gray-300">
              Показано{" "}
              <span className="font-medium text-primary-700 dark:text-primary-300">
                {visibleDepartments.length}
              </span>{" "}
              из{" "}
              <span className="font-medium text-primary-700 dark:text-primary-300">
                {filteredDepartments.length}
              </span>{" "}
              отделов
            </div>

            <nav
              className="flex justify-center sm:justify-end space-x-1"
              aria-label="Pagination"
            >
              <button
                onClick={() => handleChangePage(0)}
                disabled={page === 0}
                className={`p-2 rounded-md ${
                  page === 0
                    ? "text-gray-400 dark:text-gray-600 cursor-not-allowed"
                    : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                }`}
                aria-label="Первая страница"
              >
                <FaAngleDoubleLeft size={16} />
              </button>

              <button
                onClick={() => handleChangePage(page - 1)}
                disabled={page === 0}
                className={`p-2 rounded-md ${
                  page === 0
                    ? "text-gray-400 dark:text-gray-600 cursor-not-allowed"
                    : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                }`}
                aria-label="Предыдущая страница"
              >
                <FaChevronLeft size={16} />
              </button>

              {visiblePages.map((pageNum, idx) =>
                pageNum < 0 ? (
                  <span
                    key={`ellipsis-${idx}`}
                    className="px-2 py-2 text-gray-700 dark:text-gray-300"
                  >
                    ...
                  </span>
                ) : (
                  <button
                    key={pageNum}
                    onClick={() => handleChangePage(pageNum)}
                    className={`px-3 py-1 rounded-md text-sm font-medium ${
                      page === pageNum
                        ? "bg-primary-600 text-white dark:bg-primary-700"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                    }`}
                    aria-current={page === pageNum ? "page" : undefined}
                  >
                    {pageNum + 1}
                  </button>
                )
              )}

              <button
                onClick={() => handleChangePage(page + 1)}
                disabled={page >= totalPages - 1}
                className={`p-2 rounded-md ${
                  page >= totalPages - 1
                    ? "text-gray-400 dark:text-gray-600 cursor-not-allowed"
                    : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                }`}
                aria-label="Следующая страница"
              >
                <FaChevronRight size={16} />
              </button>

              <button
                onClick={() => handleChangePage(totalPages - 1)}
                disabled={page >= totalPages - 1}
                className={`p-2 rounded-md ${
                  page >= totalPages - 1
                    ? "text-gray-400 dark:text-gray-600 cursor-not-allowed"
                    : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                }`}
                aria-label="Последняя страница"
              >
                <FaAngleDoubleRight size={16} />
              </button>
            </nav>
          </div>
        )}
      </div>
    </div>
  );
};

export default DepartmentTable;
