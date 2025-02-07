import React, {
  useEffect,
  useState,
  useCallback,
  useMemo,
  Suspense,
} from "react";
import { motion } from "framer-motion";
import { useParams } from "react-router-dom";
import { useNavigate } from "../../RouterUtils";
import axiosInstance from "../../api";
import { apiUrl } from "../../../apiConfig";
import { StaffData, AttendanceData } from "../../schemas/IData";
import Notification from "../../components/Notification";
import LoaderComponent from "../../components/LoaderComponent";

import MobileActionButtons from "./MobileActionButtons";
import StaffHeader from "./StaffHeader";
import EmployeeInfo from "./EmployeeInfo";
import AttendanceSection from "./AttendanceSection";

const NewAbsenceModal = React.lazy(
  () => import("../../components/NewAbsenceModal")
);

const containerVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.8 } },
};

const StaffDetail: React.FC = () => {
  const { pin } = useParams<{ pin: string }>();
  const navigate = useNavigate();

  const [staffData, setStaffData] = useState<StaffData | null>(null);
  const [attendance, setAttendance] = useState<Record<string, AttendanceData>>(
    {}
  );
  const [startDate, setStartDate] = useState<string>(
    new Date(new Date().setDate(new Date().getDate() - 7))
      .toISOString()
      .split("T")[0]
  );
  const [endDate, setEndDate] = useState<string>(
    new Date().toISOString().split("T")[0]
  );
  const [notificationMessage, setNotificationMessage] = useState("");
  const [notificationType, setNotificationType] = useState<"warning" | "error">(
    "error"
  );
  const [showNotification, setShowNotification] = useState(false);
  const [loading, setLoading] = useState(true);
  const [isFirstLoad, setIsFirstLoad] = useState(true);
  const [showAbsenceModal, setShowAbsenceModal] = useState(false);

  const fetchAttendanceData = useCallback(async () => {
    if (startDate && endDate && new Date(startDate) <= new Date(endDate)) {
      if (isFirstLoad) {
        setLoading(true);
        setIsFirstLoad(false);
      }
      try {
        const params = { start_date: startDate, end_date: endDate };
        const res = await axiosInstance.get(`${apiUrl}/api/staff/${pin}`, {
          params,
        });
        setStaffData(res.data);
        setAttendance(res.data.attendance);
      } catch (error: any) {
        if (error.response && error.response.status === 404) {
          setNotificationMessage("Сотрудник не найден");
          setNotificationType("error");
          setShowNotification(true);
        } else {
          setNotificationMessage("Произошла ошибка при загрузке данных.");
          setNotificationType("error");
          setShowNotification(true);
          console.error(`Error fetching attendance data: ${error}`);
        }
      } finally {
        setLoading(false);
      }
    }
  }, [startDate, endDate, pin, isFirstLoad]);

  useEffect(() => {
    fetchAttendanceData();
  }, [startDate, endDate, fetchAttendanceData]);

  const handleStartDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newStartDate = e.target.value;
    setStartDate(newStartDate);
    if (new Date(newStartDate) > new Date(endDate)) {
      setEndDate(newStartDate);
    }
  };

  const handleEndDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newEndDate = e.target.value;
    setEndDate(newEndDate);
    if (new Date(newEndDate) < new Date(startDate)) {
      setStartDate(newEndDate);
    }
  };

  const navigateToChildDepartment = useCallback(() => {
    if (staffData) {
      navigate(`/childDepartment/${staffData.department_id}`);
    }
  }, [navigate, staffData]);

  const generateLegendItems = useCallback(
    (attendanceData: Record<string, AttendanceData>) => {
      const legend = new Set<string>();
      const defaultText = "Отсутствует (Не одобрено)";

      Object.values(attendanceData).forEach((data) => {
        if (data.is_remote_work) {
          legend.add("Удаленная работа");
        } else if (data.absent_reason && data.absent_reason.trim() !== "") {
          legend.add(
            data.is_absent_approved
              ? `Одобрено: ${data.absent_reason}`
              : `Не одобрено: ${data.absent_reason}`
          );
        } else if (data.is_weekend) {
          if (
            data.first_in &&
            data.first_in.trim() !== "" &&
            data.last_out &&
            data.last_out.trim() !== ""
          ) {
            legend.add("Работа в выходной");
          } else {
            legend.add("Выходной день");
          }
        } else if (
          !data.first_in ||
          data.first_in.trim() === "" ||
          !data.last_out ||
          data.last_out.trim() === ""
        ) {
          legend.add(defaultText);
        }
      });

      return Array.from(legend);
    },
    []
  );

  const legendItems = useMemo(
    () => generateLegendItems(attendance),
    [attendance, generateLegendItems]
  );

  const handleDownloadExcel = async () => {
    if (!staffData) return;
    try {
      const { generateAndDownloadExcel } = await import(
        "../../utils/excelUtils"
      );
      generateAndDownloadExcel(staffData, startDate, endDate);
    } catch (error) {
      console.error("Ошибка при генерации Excel:", error);
      setNotificationMessage("Не удалось создать Excel-файл.");
      setNotificationType("error");
      setShowNotification(true);
    }
  };

  const handleDownloadZip = async () => {
    if (!staffData) return;
    try {
      const res = await axiosInstance.get(`${apiUrl}/api/absent_staff/`, {
        params: {
          start_date: startDate,
          end_date: endDate,
          staff_pin: pin,
          download: "true",
        },
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: "application/zip" });
      const link = document.createElement("a");
      link.href = window.URL.createObjectURL(blob);
      link.download = `documents_${startDate}_${endDate}.zip`;
      link.click();
    } catch (error) {
      console.error("Ошибка при скачивании ZIP:", error);
      setNotificationMessage("Не удалось скачать архив отсутствий.");
      setNotificationType("error");
      setShowNotification(true);
    }
  };

  const hasAbsenceWithReason = useMemo(() => {
    return Object.values(attendance).some(
      (record) => record.absent_reason && record.absent_reason.trim() !== ""
    );
  }, [attendance]);

  return (
    <motion.div
      className="min-h-screen py-8 px-4 sm:px-8 lg:px-24"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {loading ? (
        <LoaderComponent />
      ) : (
        <>
          {showNotification && (
            <Notification
              message={notificationMessage}
              type={notificationType}
              link="/"
            />
          )}

          {/* Мобильные кнопки */}
          <MobileActionButtons
            navigateToChildDepartment={navigateToChildDepartment}
            setShowAbsenceModal={setShowAbsenceModal}
            handleDownloadExcel={handleDownloadExcel}
            handleDownloadZip={handleDownloadZip}
            hasAbsenceWithReason={hasAbsenceWithReason}
          />

          {/* Модальное окно для добавления отсутствия */}
          {showAbsenceModal && pin && (
            <Suspense fallback={<LoaderComponent />}>
              <NewAbsenceModal
                staffPin={pin}
                onClose={() => setShowAbsenceModal(false)}
                onSuccess={fetchAttendanceData}
              />
            </Suspense>
          )}

          {staffData && (
            <div className="w-full max-w-7xl lg:max-w-screen-2xl mx-auto bg-white dark:bg-gray-900 shadow-2xl rounded-xl overflow-hidden">
              {/* Хедер */}
              <StaffHeader
                staffData={staffData}
                navigateToChildDepartment={navigateToChildDepartment}
                handleDownloadExcel={handleDownloadExcel}
                handleDownloadZip={handleDownloadZip}
                setShowAbsenceModal={setShowAbsenceModal}
                hasAbsenceWithReason={hasAbsenceWithReason}
              />

              {/* Информация о сотруднике */}
              <EmployeeInfo staffData={staffData} />

              {/* Секция с дополнительной информацией и таблицей посещаемости */}
              <AttendanceSection
                staffData={staffData}
                attendance={attendance}
                startDate={startDate}
                endDate={endDate}
                handleStartDateChange={handleStartDateChange}
                handleEndDateChange={handleEndDateChange}
                legendItems={legendItems}
              />
            </div>
          )}
        </>
      )}
    </motion.div>
  );
};

export default StaffDetail;
