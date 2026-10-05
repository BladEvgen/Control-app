import React, {
  useEffect,
  useState,
  useCallback,
  useMemo,
  useRef,
  Suspense,
} from "react";
import { motion } from "framer-motion";
import { useParams } from "react-router-dom";
import axiosInstance from "../../api";
import { apiUrl } from "../../../apiConfig";
import { installFaceLabAxiosLogging } from "../../faceLab/faceLabAxiosLogging";

installFaceLabAxiosLogging(axiosInstance);
import { StaffData, AttendanceData } from "../../schemas/IData";
import Notification from "../../components/Notification";
import LoaderComponent from "../../components/LoaderComponent";
import Breadcrumbs, { BreadcrumbItem } from "../../components/Breadcrumbs";
import { formatDepartmentName } from "../../utils/utils";
import { collectStaffAttendanceLegendChips } from "../../utils/attendanceDayPresentation";

import StaffHeader from "./StaffHeader";
import EmployeeInfo from "./EmployeeInfo";
import AttendanceSection from "./AttendanceSection";
import { lazyWithRetry } from "../../utils/lazyWithRetry";
import { useReportDates } from "../../hooks/useReportDates";
import {
  consumeSkipPageMotion,
  pageMotionInitial,
} from "../../utils/pageMotion";
import type { FaceCameraOverlayRef } from "../../faceLab/camera/types";

const NewAbsenceModal = lazyWithRetry(
  () => import("../../components/NewAbsenceModal"),
);

const StaffFaceCameraOverlay = lazyWithRetry(
  () => import("../../faceLab/camera/FaceCameraOverlay"),
);

const containerVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35 } },
};

const StaffDetail: React.FC = () => {
  const { pin } = useParams<{ pin: string }>();
  const skipPageMotion = useMemo(() => consumeSkipPageMotion(), []);
  const { startDate, endDate, setStartDate, setEndDate, today } =
    useReportDates();

  const [staffData, setStaffData] = useState<StaffData | null>(null);
  const [attendance, setAttendance] = useState<Record<string, AttendanceData>>(
    {},
  );
  const [notificationMessage, setNotificationMessage] = useState("");
  const [notificationType, setNotificationType] = useState<"warning" | "error">(
    "error",
  );
  const [showNotification, setShowNotification] = useState(false);
  const [loading, setLoading] = useState(true);
  const loadedPin = useRef<string | undefined>(undefined);
  const requestSequence = useRef(0);
  const [showAbsenceModal, setShowAbsenceModal] = useState(false);
  const avatarInputRef = useRef<HTMLInputElement>(null);
  const avatarCameraRef = useRef<FaceCameraOverlayRef>(null);
  const [avatarUploadBusy, setAvatarUploadBusy] = useState(false);
  const [avatarUploadMessage, setAvatarUploadMessage] = useState<string | null>(
    null,
  );
  const [faceSetupAngles, setFaceSetupAngles] = useState<{
    loading: boolean;
    done: number;
  }>({ loading: true, done: 0 });

  const refreshFaceSetupAngles = useCallback(async () => {
    if (!pin) return;
    setFaceSetupAngles((s) => ({ ...s, loading: true }));
    try {
      const res = await axiosInstance.get<{
        angles_present?: string[];
        bootstrap_complete?: boolean;
      }>(`face-lab/bootstrap-status/?pin=${encodeURIComponent(pin)}`);
      const present = new Set(
        (res.data?.angles_present ?? []).map((x) => String(x).toLowerCase()),
      );
      const req = ["front", "left", "right"] as const;
      const done = req.filter((a) => present.has(a)).length;
      const complete =
        res.data?.bootstrap_complete === true || done >= req.length;
      setFaceSetupAngles({
        loading: false,
        done: complete ? req.length : done,
      });
    } catch {
      setFaceSetupAngles({ loading: false, done: 0 });
    }
  }, [pin]);

  const fetchAttendanceData = useCallback(async () => {
    if (startDate && endDate && new Date(startDate) <= new Date(endDate)) {
      const request = ++requestSequence.current;
      if (loadedPin.current !== pin) setLoading(true);
      try {
        const params = { start_date: startDate, end_date: endDate };
        const res = await axiosInstance.get(`${apiUrl}/api/staff/${pin}`, {
          params,
        });
        if (request !== requestSequence.current) return;
        loadedPin.current = pin;
        setStaffData(res.data);
        setAttendance(res.data.attendance);
        setShowNotification(false);
      } catch (error: unknown) {
        if (request !== requestSequence.current) return;
        if (
          error &&
          typeof error === "object" &&
          "response" in error &&
          error.response &&
          typeof error.response === "object" &&
          "status" in error.response &&
          error.response.status === 404
        ) {
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
        if (request === requestSequence.current) setLoading(false);
      }
    }
  }, [startDate, endDate, pin]);

  useEffect(() => {
    const sequence = requestSequence;
    fetchAttendanceData();
    return () => {
      sequence.current++;
    };
  }, [startDate, endDate, fetchAttendanceData]);

  useEffect(() => {
    if (!pin || !staffData) return;
    void refreshFaceSetupAngles();
  }, [pin, staffData, refreshFaceSetupAngles]);

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

  const attendanceLegendChips = useMemo(
    () => collectStaffAttendanceLegendChips(attendance),
    [attendance],
  );

  const handleDownloadExcel = async () => {
    if (!staffData) return;
    try {
      const { generateAndDownloadExcel } =
        await import("../../utils/excelUtils");
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
      (record) => record.absent_reason && record.absent_reason.trim() !== "",
    );
  }, [attendance]);

  const breadcrumbs = useMemo((): BreadcrumbItem[] => {
    const items: BreadcrumbItem[] = [];

    const path = staffData?.breadcrumb_path ?? [];
    if (path.length > 0) {
      path.forEach((item, idx) => {
        const isOwnDepartment = idx === path.length - 1;
        items.push({
          label: formatDepartmentName(item.name),
          path: isOwnDepartment
            ? `/childDepartment/${item.id}?direct=1`
            : `/department/${item.id}`,
        });
      });
    } else if (staffData?.department_id) {
      items.push({
        label: formatDepartmentName(staffData.department || ""),
        path: `/childDepartment/${staffData.department_id}?direct=1`,
      });
    }

    if (staffData) {
      items.push({
        label: `${staffData.surname} ${staffData.name}`,
      });
    }

    return items;
  }, [staffData]);

  const uploadAvatarFile = useCallback(
    async (file: File) => {
      if (!pin) return;
      setAvatarUploadMessage(null);
      setAvatarUploadBusy(true);
      try {
        const fd = new FormData();
        fd.append("image", file);
        await axiosInstance.put(`staff/${encodeURIComponent(pin)}/avatar/`, fd);
        setAvatarUploadMessage("Фото профиля обновлено.");
        await fetchAttendanceData();
        await refreshFaceSetupAngles();
      } catch {
        setAvatarUploadMessage(
          "Не удалось обновить фото. Попробуйте снова или другой файл (PNG или JPEG).",
        );
      } finally {
        setAvatarUploadBusy(false);
      }
    },
    [pin, fetchAttendanceData, refreshFaceSetupAngles],
  );

  const handleAvatarFileSelected = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0];
      e.target.value = "";
      if (!f) return;
      await uploadAvatarFile(f);
    },
    [uploadAvatarFile],
  );

  const handleAvatarCameraShot = useCallback(
    (blob: Blob) => {
      const file = new File([blob], "profile-photo.jpg", {
        type: blob.type || "image/jpeg",
      });
      void uploadAvatarFile(file);
    },
    [uploadAvatarFile],
  );

  useEffect(() => {
    const scrollButton = document.querySelector(
      '[aria-label="Прокрутить наверх"]',
    ) as HTMLElement;
    if (scrollButton) {
      scrollButton.style.display = "none";
    }
    return () => {
      if (scrollButton) {
        scrollButton.style.display = "";
      }
    };
  }, []);

  return (
    <motion.div
      className="min-w-0"
      variants={containerVariants}
      initial={pageMotionInitial(skipPageMotion) ?? "hidden"}
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
            <div className="mx-auto w-full min-w-0 max-w-7xl lg:max-w-screen-2xl">
              {/* Breadcrumbs */}
              <motion.div
                className="mb-4 sm:mb-6"
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
              >
                <Breadcrumbs items={breadcrumbs} />
              </motion.div>

              <div className="min-w-0">
                {pin ? (
                  <>
                    <input
                      ref={avatarInputRef}
                      type="file"
                      accept="image/png,image/jpeg,.png,.jpg,.jpeg,.PNG,.JPG,.JPEG"
                      className="sr-only"
                      aria-label="Выбор фото для профиля с устройства"
                      onChange={handleAvatarFileSelected}
                    />
                    <Suspense fallback={null}>
                      <StaffFaceCameraOverlay
                        ref={avatarCameraRef}
                        onShot={handleAvatarCameraShot}
                        requireLiveness={false}
                        guidanceContext="profile_photo"
                        voiceLang="off"
                      />
                    </Suspense>
                  </>
                ) : null}
                {/* Хедер */}
                <StaffHeader
                  staffData={staffData}
                  handleDownloadExcel={handleDownloadExcel}
                  handleDownloadZip={handleDownloadZip}
                  setShowAbsenceModal={setShowAbsenceModal}
                  hasAbsenceWithReason={hasAbsenceWithReason}
                  staffPin={pin}
                  onOpenAvatarFromFile={() => avatarInputRef.current?.click()}
                  onOpenAvatarFromCamera={() =>
                    void avatarCameraRef.current?.open("user")
                  }
                  avatarUploadBusy={avatarUploadBusy}
                  avatarActionMessage={avatarUploadMessage}
                  faceSetupAnglesDone={faceSetupAngles.done}
                  faceSetupAnglesLoading={faceSetupAngles.loading}
                />

                {/* Информация о сотруднике */}
                <EmployeeInfo staffData={staffData} />

                {/* Секция с дополнительной информацией и таблицей посещаемости */}
                <AttendanceSection
                  staffData={staffData}
                  attendance={attendance}
                  lessonAttendanceAudit={
                    staffData.lesson_attendance_audit ?? {}
                  }
                  startDate={startDate}
                  endDate={endDate}
                  handleStartDateChange={handleStartDateChange}
                  handleEndDateChange={handleEndDateChange}
                  attendanceLegendChips={attendanceLegendChips}
                  today={today}
                />
              </div>
            </div>
          )}
        </>
      )}
    </motion.div>
  );
};

export default StaffDetail;
