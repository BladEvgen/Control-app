import {
  useState,
  useEffect,
  useReducer,
  ChangeEvent,
  useCallback,
  useMemo,
} from "react";
import { IData, IChildDepartment } from "../schemas/IData";
import { useParams } from "react-router-dom";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { formatDepartmentName } from "../utils/utils";
import DepartmentTable from "./DepartmentTable";
import LoaderComponent from "../components/LoaderComponent";
import Notification from "../components/Notification";
import DateFilterBar from "../components/DateFilterBar";
import Breadcrumbs from "../components/Breadcrumbs";
import { runAttendanceExcelDownload } from "../utils/attendanceExcelDownloadHub";
import { FaBuilding } from "react-icons/fa";
import { motion, AnimatePresence } from "framer-motion";
import { cacheManager } from "../utils/cache";

class BaseAction<T> {
  static SET_LOADING = "SET_LOADING";
  static SET_DATA = "SET_DATA";
  static SET_ERROR = "SET_ERROR";
  type: string;
  payload: T;
  constructor(type: string, payload: T) {
    this.type = type;
    this.payload = payload;
  }
}

type DepartmentActionPayload = IData | boolean | string | null;

class DepartmentAction extends BaseAction<DepartmentActionPayload> {
  static SET_LOADING = "SET_LOADING";
  static SET_DATA = "SET_DATA";
  static SET_ERROR = "SET_ERROR";
}

interface DepartmentState {
  data: IData;
  loading: boolean;
  error: string | null;
}

const initialState: DepartmentState = {
  data: {
    name: "",
    date_of_creation: "",
    child_departments: [],
    total_staff_count: 0,
  },
  loading: true,
  error: null,
};

const reducer = (
  state: DepartmentState,
  action: DepartmentAction,
): DepartmentState => {
  switch (action.type) {
    case DepartmentAction.SET_LOADING:
      return { ...state, loading: action.payload as boolean };
    case DepartmentAction.SET_DATA:
      return {
        ...state,
        data: action.payload as IData,
        loading: false,
        error: null,
      };
    case DepartmentAction.SET_ERROR:
      return {
        ...state,
        error: action.payload as string | null,
        loading: false,
      };
    default:
      return state;
  }
};

const shouldRenderLink = (hasDepartmentId: boolean): boolean => {
  return Boolean(hasDepartmentId);
};

const DepartmentPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const departmentId = id ?? null;

  const getFormattedDate = (date: Date): string =>
    date.toISOString().split("T")[0];

  const todayDate = new Date();
  const yesterdayDate = new Date(todayDate);
  yesterdayDate.setDate(yesterdayDate.getDate() - 1);
  const startInitialDate = new Date(yesterdayDate);
  startInitialDate.setDate(startInitialDate.getDate() - 7);

  const [state, dispatch] = useReducer(reducer, initialState);
  const { data, loading, error } = state;

  const [endDate, setEndDate] = useState<string>(
    getFormattedDate(yesterdayDate),
  );
  const [startDate, setStartDate] = useState<string>(
    getFormattedDate(startInitialDate),
  );
  const today = getFormattedDate(todayDate);


  const canDownload = Boolean(startDate && endDate && departmentId);

  const fetchRootDepartments = useCallback(async (forceRefresh = false) => {
    const cacheKey = "root_departments";

    if (!forceRefresh) {
      const cachedData = cacheManager.get<IData>(cacheKey);
      if (cachedData) {
        dispatch(new DepartmentAction(DepartmentAction.SET_DATA, cachedData));
        return;
      }
    } else {
      cacheManager.invalidate(cacheKey);
    }

    dispatch(new DepartmentAction(DepartmentAction.SET_LOADING, true));
    try {
      const response = await axiosInstance.get(
        `${apiUrl}/api/departments/root/`,
      );

      interface RootDepartmentItem {
        child_id: string;
        name: string;
        date_of_creation: string;
        parent: string;
        has_child_departments: boolean;
        total_staff_count: number;
        child_departments: Array<{
          child_id: string;
          name: string;
          date_of_creation: string;
          parent: string;
        }>;
      }

      interface RootDepartmentResponse {
        departments: RootDepartmentItem[];
        total_staff_count: number;
      }

      const batchData = response.data as RootDepartmentResponse;
      const departments = batchData.departments || [];

      const virtualChildren: IChildDepartment[] = departments.map(
        (d: RootDepartmentItem) => ({
          child_id: d.child_id,
          name: d.name ?? String(d.child_id),
          date_of_creation: d.date_of_creation ?? "",
          parent: "",
          has_child_departments: d.has_child_departments ?? false,
        }),
      );

      const virtualRoot: IData = {
        name: "Структура Университета",
        date_of_creation: "",
        child_departments: virtualChildren,
        total_staff_count: batchData.total_staff_count || 0,
      };

      cacheManager.set(cacheKey, virtualRoot);
      dispatch(new DepartmentAction(DepartmentAction.SET_DATA, virtualRoot));
    } catch (err) {
      console.error("fetchRootDepartments failed:", err);
      dispatch(
        new DepartmentAction(
          DepartmentAction.SET_ERROR,
          "Не удалось загрузить корневые отделы. Пожалуйста, попробуйте позже.",
        ),
      );
    }
  }, []);

  const fetchDepartmentData = useCallback(
    async (id: string, forceRefresh = false) => {
      const cacheKey = `department_${id}`;

      if (!forceRefresh) {
        const cachedData = cacheManager.get<IData>(cacheKey);
        if (cachedData) {
          dispatch(new DepartmentAction(DepartmentAction.SET_DATA, cachedData));
          return;
        }
      } else {
        cacheManager.invalidate(cacheKey);
      }

      dispatch(new DepartmentAction(DepartmentAction.SET_LOADING, true));
      try {
        const res = await axiosInstance.get(`${apiUrl}/api/department/${id}/`, {
          timeout: 30000,
        });
        cacheManager.set(cacheKey, res.data);
        dispatch(new DepartmentAction(DepartmentAction.SET_DATA, res.data));
      } catch (err) {
        console.error(`Error: ${err}`);
        dispatch(
          new DepartmentAction(
            DepartmentAction.SET_ERROR,
            "Не удалось загрузить данные. Пожалуйста, попробуйте позже.",
          ),
        );
      }
    },
    [],
  );

  useEffect(() => {
    if (departmentId) {
      fetchDepartmentData(departmentId);
    } else {
      fetchRootDepartments();
    }
  }, [departmentId, fetchDepartmentData, fetchRootDepartments]);

  const handleStartDateChange = (e: ChangeEvent<HTMLInputElement>) => {
    const newDate = e.target.value;
    setStartDate(newDate);
    if (newDate > endDate) {
      setEndDate(newDate);
    }
  };

  const handleEndDateChange = (e: ChangeEvent<HTMLInputElement>) => {
    const newDate = e.target.value;
    setEndDate(newDate);
    if (newDate < startDate) {
      setStartDate(newDate);
    }
  };

  const handleDownload = useCallback(() => {
    if (!canDownload) return;
    const departmentName = data.name.replace(/\s/g, "_");
    void runAttendanceExcelDownload({
      url: `${apiUrl}/api/download/${departmentId}/`,
      params: { startDate, endDate },
      filename: `Посещаемость_${departmentName}.xlsx`,
      holdKey: departmentId ?? undefined,
    });
  }, [canDownload, departmentId, data.name, startDate, endDate]);

  const pageVariants = useMemo(
    () => ({
      initial: { opacity: 0 },
      animate: {
        opacity: 1,
        transition: {
          staggerChildren: 0.1,
          when: "beforeChildren",
        },
      },
      exit: { opacity: 0 },
    }),
    [],
  );

  const itemVariants = useMemo(
    () => ({
      initial: { opacity: 0, y: 20 },
      animate: { opacity: 1, y: 0 },
      exit: { opacity: 0, y: -20 },
    }),
    [],
  );

  const breadcrumbs = useMemo(() => {
    if (!departmentId) return [];
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
    return [{ label: formatDepartmentName(data?.name || "") }];
  }, [departmentId, data?.name, data?.breadcrumb_path]);

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key="department-page"
        className="page-shell"
        variants={pageVariants}
        initial="initial"
        animate="animate"
        exit="exit"
      >
        {loading ? (
          <LoaderComponent />
        ) : error ? (
          <Notification
            message={error}
            type="error"
            link="/"
            linkText="Вернуться на главную"
          />
        ) : (
          <>
            <motion.div className="mb-6 space-y-4" variants={itemVariants}>
              <div className="flex items-center justify-center md:justify-start">
                <FaBuilding className="text-primary-600 dark:text-primary-400 mr-3 text-2xl md:text-3xl" />
                <h1 className="section-title mb-0">
                  {formatDepartmentName(data?.name)}
                </h1>
              </div>
              {shouldRenderLink(!!departmentId) && breadcrumbs.length > 0 && (
                <Breadcrumbs items={breadcrumbs} />
              )}
            </motion.div>

            {shouldRenderLink(!!departmentId) && (
              <motion.div variants={itemVariants} className="mt-6 mb-8">
                <DateFilterBar
                  startDate={startDate}
                  endDate={endDate}
                  onStartDateChange={handleStartDateChange}
                  onEndDateChange={handleEndDateChange}
                  onDownload={handleDownload}
                  isDownloadDisabled={!canDownload}
                  excelHoldKey={departmentId}
                  today={today}
                />
              </motion.div>
            )}

            {data && (
              <motion.div
                variants={itemVariants}
                className="card overflow-hidden p-0"
              >
                <DepartmentTable data={data} />
              </motion.div>
            )}
          </>
        )}
      </motion.div>
    </AnimatePresence>
  );
};

export default DepartmentPage;
