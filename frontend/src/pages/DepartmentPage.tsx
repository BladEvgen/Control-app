import { useState, useEffect, useReducer, ChangeEvent } from "react";
import { IData } from "../schemas/IData";
import { useParams, useLocation, useNavigate } from "react-router-dom";
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
import { FaHome } from "react-icons/fa";
import { motion } from "framer-motion";

class BaseAction<T> {
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

const shouldRenderLink = (pathname: string): boolean => {
  const excludedPaths = ["/app/", "/app/department/1", "/app"];
  return !excludedPaths.includes(pathname);
};

const DepartmentPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const departmentId = id ? id : "1";

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
          "Не удалось загрузить данные"
        )
      );
    }
  };

  useEffect(() => {
    fetchDepartmentData(departmentId);
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

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.5 }}
        className="container mx-auto px-4 py-8 dark:text-white"
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
            <h1 className="text-3xl font-bold text-center md:text-left text-white mb-8">
              {formatDepartmentName(data?.name)}
            </h1>

            {shouldRenderLink(location.pathname) && (
              <DesktopNavigation
                onHomeClick={() => navigate("/")}
                visibleButtons={["home"]}
              />
            )}

            {shouldRenderLink(location.pathname) && (
              <DateFilterBar
                startDate={startDate}
                endDate={endDate}
                onStartDateChange={handleStartDateChange}
                onEndDateChange={handleEndDateChange}
                onDownload={handleDownload}
                isDownloading={isDownloading}
                isDownloadDisabled={!startDate || !endDate}
                today={today}
              />
            )}

            {showWaitMessage && (
              <div className="mx-auto max-w-md my-4">
                <WaitNotification />
              </div>
            )}

            {data && <DepartmentTable data={data} />}
          </>
        )}
      </motion.div>

      {/* Плавающая кнопка для мобильных устройств */}
      {!loading && !error && shouldRenderLink(location.pathname) && (
        <motion.div
          initial={{ opacity: 0, y: 50 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          whileHover={{ scale: 1.1 }}
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
    </>
  );
};

export default DepartmentPage;
