import { useNavigate } from "../RouterUtils";
import {
  useState,
  useEffect,
  useCallback,
  useMemo,
  memo,
  lazy,
  Suspense,
} from "react";
import { useParams } from "react-router-dom";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { IChildDepartmentData } from "../schemas/IData";
import { formatDepartmentName } from "../utils/utils";
import { cacheManager } from "../utils/cache";
import { consumeSkipPageMotion, pageMotionInitial } from "../utils/pageMotion";
import {
  FaUserCheck,
  FaUserTimes,
  FaBuilding,
  FaUsers,
  FaChartBar,
  FaChevronDown,
  FaChevronUp,
} from "react-icons/fa";
import { motion, AnimatePresence } from "framer-motion";
import LoaderComponent from "../components/LoaderComponent";
import Breadcrumbs from "../components/Breadcrumbs";
import DateFilterBar from "../components/DateFilterBar";
import SearchInput from "../components/SearchInput";
import { runAttendanceExcelDownload } from "../utils/attendanceExcelDownloadHub";

const LazyDashboard = lazy(() => import("./Dashboard"));

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

  const [showDashboard, setShowDashboard] = useState<boolean>(false);
  const navigate = useNavigate();

  const dispatch = (
    action: BaseAction<boolean | IChildDepartmentData | string | null>,
  ) => {
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
    const fetchData = async (forceRefresh = false) => {
      if (!id) return;

      const cacheKey = `child_department_${id}`;
      if (!forceRefresh) {
        const cachedData = cacheManager.get<IChildDepartmentData>(cacheKey);
        if (cachedData) {
          dispatch(new BaseAction(BaseAction.SET_DATA, cachedData));
          return;
        }
      } else {
        cacheManager.invalidate(cacheKey);
      }

      dispatch(new BaseAction(BaseAction.SET_LOADING, true));
      try {
        const res = await axiosInstance.get(
          `${apiUrl}/api/child_department/${id}/`,
        );
        cacheManager.set(cacheKey, res.data);
        dispatch(new BaseAction(BaseAction.SET_DATA, res.data));
      } catch (err) {
        console.error("Error:", err);
        dispatch(
          new BaseAction(
            BaseAction.SET_ERROR,
            "Не удалось загрузить данные. Пожалуйста, попробуйте еще раз.",
          ),
        );
      }
    };
    if (id) fetchData();
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

  const navigateToParent = useCallback(() => {
    if (data?.child_department.parent) {
      navigate(`/department/${data.child_department.parent}`);
    } else {
      navigate("/");
    }
  }, [data?.child_department.parent, navigate]);

  const handleRowClick = useCallback(
    (pin: string) => {
      navigate(`/staffDetail/${pin}`);
    },
    [navigate],
  );

  const breadcrumbs = useMemo(() => {
    const path = data?.breadcrumb_path;
    if (path && path.length > 0) {
      return path.map((item, idx) => {
        const isLast = idx === path.length - 1;
        return {
          label: formatDepartmentName(item.name),
          path: isLast ? undefined : `/department/${item.id}`,
        };
      });
    }
    const items: Array<{ label: string; path?: string; onClick?: () => void }> =
      [];
    if (data?.child_department.parent) {
      items.push({
        label: "Отделы",
        onClick: navigateToParent,
      });
    }
    if (data?.child_department?.name) {
      items.push({ label: formatDepartmentName(data.child_department.name) });
    }
    return items;
  }, [data?.child_department, data?.breadcrumb_path, navigateToParent]);

  const handleDownload = useCallback(() => {
    if (!id) return;

    let departmentName = "";
    if (data && data.child_department) {
      departmentName = data.child_department.name
        ? data.child_department.name.replace(/\s/g, "_")
        : String(data.child_department.child_id);
    }

    void runAttendanceExcelDownload({
      url: `${apiUrl}/api/download/${id}/`,
      params: { startDate, endDate },
      filename: `Посещаемость_${departmentName}.xlsx`,
      holdKey: id,
    });
  }, [id, startDate, endDate, data]);

  const isDownloadDisabled = !startDate || !endDate;

  const filteredStaff = useMemo(
    () =>
      data?.staff_data
        ? Object.entries(data.staff_data).filter(([, staff]) =>
            staff.FIO.toLowerCase().includes(searchQuery.toLowerCase()),
          )
        : [],
    [data?.staff_data, searchQuery],
  );

  const skipPageMotion = useMemo(() => consumeSkipPageMotion(), []);

  const containerVariants = useMemo(
    () => ({
      hidden: { opacity: 0 },
      visible: {
        opacity: 1,
        transition: {
          staggerChildren: 0.1,
          delayChildren: 0.2,
        },
      },
    }),
    [],
  );

  const itemVariants = useMemo(
    () => ({
      hidden: { opacity: 0, y: 10 },
      visible: { opacity: 1, y: 0 },
    }),
    [],
  );

  return (
    <AnimatePresence mode="sync">
      <motion.div
        className="page-shell"
        variants={containerVariants}
        initial={pageMotionInitial(skipPageMotion) ?? "hidden"}
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
            <motion.button
              onClick={() => navigate("/")}
              className="btn-primary mt-4"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              Вернуться на главную
            </motion.button>
          </motion.div>
        ) : (
          <>
            <motion.div className="mb-6 space-y-4" variants={itemVariants}>
              <div className="flex items-center">
                <FaBuilding className="text-primary-600 dark:text-primary-400 mr-3 text-2xl md:text-3xl" />
                <h1 className="section-title mb-0">
                  {data?.child_department?.name &&
                    formatDepartmentName(data.child_department.name)}
                </h1>
              </div>
              <Breadcrumbs items={breadcrumbs} />
            </motion.div>

            <motion.div variants={itemVariants} className="mt-6 mb-6">
              <DateFilterBar
                startDate={startDate}
                endDate={endDate}
                onStartDateChange={handleStartDateChange}
                onEndDateChange={handleEndDateChange}
                onDownload={handleDownload}
                isDownloadDisabled={isDownloadDisabled}
                excelHoldKey={id ?? null}
                today={today}
                idPrefix="child-department"
              />
            </motion.div>

            <motion.div variants={itemVariants} className="mb-6">
              <button
                type="button"
                onClick={() => setShowDashboard((v) => !v)}
                className="panel-toggle"
                aria-expanded={showDashboard}
              >
                <span className="flex items-center gap-2 font-medium text-primary-700 dark:text-primary-300">
                  <FaChartBar className="text-lg" />
                  {showDashboard
                    ? "Свернуть график посещаемости за день"
                    : "Показать график посещаемости за день"}
                </span>
                {showDashboard ? (
                  <FaChevronUp className="text-gray-500" />
                ) : (
                  <FaChevronDown className="text-gray-500" />
                )}
              </button>
              <AnimatePresence>
                {showDashboard && id && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="inset-panel">
                      <Suspense fallback={<LoaderComponent />}>
                        <LazyDashboard pin={id} />
                      </Suspense>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>

            <motion.div variants={itemVariants} className="mb-6 card p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
                <div className="min-w-0 flex-1">
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
                <div className="w-full min-w-0 lg:max-w-sm lg:shrink-0">
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
              className="block lg:hidden space-y-4"
              variants={containerVariants}
              initial="hidden"
              animate="visible"
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
                    className="card p-5 cursor-pointer"
                    onClick={() => handleRowClick(pin)}
                  >
                    <div className="flex justify-between items-start">
                      <span className="text-primary-700 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300 font-semibold text-lg transition-colors">
                        {staff.FIO}
                      </span>
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
                              staff.date_of_creation,
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
              className="hidden lg:block card overflow-hidden p-0"
            >
              <div className="data-table-wrap -mx-px">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-800">
                  <thead className="bg-primary-50/90 dark:bg-gray-900">
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
                      <th
                        scope="col"
                        className="relative px-6 py-3.5 text-left text-sm font-semibold uppercase tracking-wider text-primary-900 dark:text-primary-100"
                      >
                        <span className="sr-only">Просмотр</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 bg-white dark:divide-gray-800 dark:bg-gray-950">
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
                          className="cursor-pointer transition-colors duration-200 hover:bg-primary-50/80 dark:hover:bg-gray-900/85"
                          onClick={() => handleRowClick(pin)}
                        >
                          <td className="px-6 py-4 whitespace-nowrap">
                            <span className="text-primary-700 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300 font-medium transition-colors">
                              {staff.FIO}
                            </span>
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
                              staff.date_of_creation,
                            ).toLocaleDateString()}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap">
                            {staff.avatar ? (
                              <span className="badge-success">
                                <FaUserCheck className="mr-1" /> Верифицирован
                              </span>
                            ) : (
                              <span className="badge-danger">
                                <FaUserTimes className="mr-1" /> Не
                                верифицирован
                              </span>
                            )}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                            <span className="badge-primary px-3 py-1.5 rounded-lg">
                              Показать детали
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </motion.div>
          </>
        )}
      </motion.div>
    </AnimatePresence>
  );
};

export default memo(ChildDepartmentPage);
