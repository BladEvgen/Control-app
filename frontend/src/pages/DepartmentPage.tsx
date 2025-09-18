import { useState, useEffect, useReducer, ChangeEvent } from "react";
import { IData, IChildDepartment } from "../schemas/IData";
import { useParams, useNavigate } from "react-router-dom";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { formatDepartmentName } from "../utils/utils";
import DepartmentTable from "./DepartmentTable";
import LoaderComponent from "../components/LoaderComponent";
import Notification from "../components/Notification";
import DateFilterBar from "../components/DateFilterBar";
import DesktopNavigation from "../components/DesktopNavigation";
import WaitNotification from "../components/WaitNotification";
import useWaitNotification from "../hooks/useWaitNotification";
import { FloatingButton } from "../components/FloatingButton";
import { FaHome, FaBuilding } from "react-icons/fa";
import { motion, AnimatePresence } from "framer-motion";

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

class DepartmentAction extends BaseAction<any> {
  static SET_LOADING = "SET_LOADING";
  static SET_DATA = "SET_DATA";
  static SET_ERROR = "SET_ERROR";
}

interface DepartmentState {
  data: IData;
  mode?: "root" | "department";
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
  action: DepartmentAction
): DepartmentState => {
  switch (action.type) {
    case DepartmentAction.SET_LOADING:
      return { ...state, loading: action.payload };
    case DepartmentAction.SET_DATA:
      return { ...state, data: action.payload, loading: false, error: null };
    case DepartmentAction.SET_ERROR:
      return { ...state, error: action.payload, loading: false };
    default:
      return state;
  }
};

const shouldRenderLink = (hasDepartmentId: boolean): boolean => {
  return Boolean(hasDepartmentId);
};

const DepartmentPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
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
    getFormattedDate(yesterdayDate)
  );
  const [startDate, setStartDate] = useState<string>(
    getFormattedDate(startInitialDate)
  );
  const [isDownloading, setIsDownloading] = useState<boolean>(false);
  const today = getFormattedDate(todayDate);

  const { showWaitMessage, startWaitNotification, clearWaitNotification } =
    useWaitNotification();

  const canDownload = Boolean(
    startDate && endDate && departmentId && departmentId !== "1"
  );

  const fetchRootDepartments = async () => {
    dispatch(new DepartmentAction(DepartmentAction.SET_LOADING, true));
    try {
      const idsRes = await axiosInstance.get(
        `${apiUrl}/api/parent_department_id/`
      );
      const ids: string[] = idsRes.data ?? [];
      const results = await Promise.all(
        ids.map((depId) =>
          axiosInstance.get(`${apiUrl}/api/department/${depId}/`)
        )
      );
      const virtualChildren: IChildDepartment[] = ids.map((depId, idx) => {
        const d = results[idx].data as IData;
        const hasKids =
          Array.isArray(d.child_departments) && d.child_departments.length > 0;
        const created = d.date_of_creation ?? "";
        return {
          child_id: depId,
          name: d.name ?? String(depId),
          date_of_creation: created,
          parent: "",
          has_child_departments: !!hasKids,
        };
      });
      const virtualRoot: IData = {
        name: "Структура Университета",
        date_of_creation: "",
        child_departments: virtualChildren,
        total_staff_count: results.reduce(
          (sum, r) => sum + (Number(r.data?.total_staff_count) || 0),
          0
        ),
      };
      dispatch(new DepartmentAction(DepartmentAction.SET_DATA, virtualRoot));
    } catch (err) {
      dispatch(
        new DepartmentAction(
          DepartmentAction.SET_ERROR,
          "Не удалось загрузить корневые отделы. Пожалуйста, попробуйте позже."
        )
      );
    }
  };

  const fetchDepartmentData = async (id: string) => {
    dispatch(new DepartmentAction(DepartmentAction.SET_LOADING, true));
    try {
      const res = await axiosInstance.get(`${apiUrl}/api/department/${id}/`);
      dispatch(new DepartmentAction(DepartmentAction.SET_DATA, res.data));
    } catch (err) {
      console.error(`Error: ${err}`);
      dispatch(
        new DepartmentAction(
          DepartmentAction.SET_ERROR,
          "Не удалось загрузить данные. Пожалуйста, попробуйте позже."
        )
      );
    }
  };

  useEffect(() => {
    if (departmentId) {
      fetchDepartmentData(departmentId);
    } else {
      fetchRootDepartments();
    }
  }, [departmentId]);

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

  const handleDownload = async () => {
    if (!canDownload) return;
    setIsDownloading(true);
    clearWaitNotification();
    startWaitNotification();
    try {
      const response = await axiosInstance.get(
        `${apiUrl}/api/download/${departmentId}/`,
        {
          params: { startDate, endDate },
          responseType: "blob",
          timeout: 600000,
        }
      );
      clearWaitNotification();
      setIsDownloading(false);
      const departmentName = data.name.replace(/\s/g, "_");
      const fileUrl = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = fileUrl;
      link.setAttribute("download", `Посещаемость_${departmentName}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.parentNode?.removeChild(link);
    } catch (err) {
      console.error("Error downloading the file:", err);
      clearWaitNotification();
      setIsDownloading(false);
    }
  };

  const pageVariants = {
    initial: { opacity: 0 },
    animate: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
        when: "beforeChildren",
      },
    },
    exit: { opacity: 0 },
  };

  const itemVariants = {
    initial: { opacity: 0, y: 20 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -20 },
  };

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key="department-page"
        className="max-w-7xl mx-auto"
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
            <motion.div
              className="mb-8 flex items-center justify-center md:justify-start"
              variants={itemVariants}
            >
              <FaBuilding className="text-primary-600 dark:text-primary-400 mr-3 text-2xl md:text-3xl" />
              <h1 className="section-title mb-0">
                {formatDepartmentName(data?.name)}
              </h1>
            </motion.div>

            {shouldRenderLink(!!departmentId) && (
              <motion.div variants={itemVariants}>
                <DesktopNavigation
                  onHomeClick={() => navigate("/")}
                  visibleButtons={["home"]}
                />
              </motion.div>
            )}

            {shouldRenderLink(!!departmentId) && (
              <motion.div variants={itemVariants} className="mt-6 mb-8">
                <DateFilterBar
                  startDate={startDate}
                  endDate={endDate}
                  onStartDateChange={handleStartDateChange}
                  onEndDateChange={handleEndDateChange}
                  onDownload={handleDownload}
                  isDownloading={isDownloading}
                  isDownloadDisabled={!canDownload}
                  today={today}
                />
              </motion.div>
            )}

            {showWaitMessage && (
              <motion.div
                variants={itemVariants}
                className="mx-auto max-w-md my-6"
              >
                <WaitNotification />
              </motion.div>
            )}

            {data && (
              <motion.div
                variants={itemVariants}
                className="card overflow-hidden"
              >
                <DepartmentTable
                  data={data}
                  mode={departmentId ? "department" : "root"}
                />
              </motion.div>
            )}
          </>
        )}
      </motion.div>

      {/* Floating button for mobile devices */}
      {!loading && !error && shouldRenderLink(!!departmentId) && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="fixed bottom-4 right-4 z-50 block md:hidden"
        >
          <FloatingButton
            variant="home"
            icon={<FaHome size={24} />}
            to="/"
            position="right"
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default DepartmentPage;
