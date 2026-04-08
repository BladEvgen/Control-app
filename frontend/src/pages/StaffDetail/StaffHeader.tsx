import React from "react";
import { FaArchive, FaFileExcel } from "react-icons/fa";
import { BsPlusLg } from "react-icons/bs";
import { formatDepartmentName } from "../../utils/utils";
import { apiUrl } from "../../../apiConfig";
import { StaffData } from "../../schemas/IData";
import { motion } from "framer-motion";
import {
  ProfileAvatarWithPhotoMenu,
  ProfileFaceSetupCard,
} from "./StaffProfilePhotoHub";

interface ActionButtonProps {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  variant: "excel" | "zip" | "absence";
}

const ActionButton: React.FC<ActionButtonProps> = ({
  icon,
  label,
  onClick,
  variant,
}) => {
  const variantClasses = {
    excel:
      "bg-green-500 hover:bg-green-600 dark:bg-green-600 dark:hover:bg-green-700 text-white border-green-600 dark:border-green-700",
    zip: "bg-orange-500 hover:bg-orange-600 dark:bg-orange-600 dark:hover:bg-orange-700 text-white border-orange-600 dark:border-orange-700",
    absence:
      "bg-blue-500 hover:bg-blue-600 dark:bg-blue-600 dark:hover:bg-blue-700 text-white border-blue-600 dark:border-blue-700",
  };

  return (
    <motion.button
      onClick={onClick}
      className={`
        flex items-center gap-1.5 px-3 py-2 rounded-lg
        border-2 font-medium text-xs lg:text-sm
        transition-all duration-200
        shadow-md hover:shadow-lg
        ${variantClasses[variant]}
      `}
      whileHover={{ scale: 1.05, y: -2 }}
      whileTap={{ scale: 0.95 }}
      title={label}
      aria-label={label}
    >
      {icon}
      <span className="hidden lg:inline">{label}</span>
    </motion.button>
  );
};

const CONTRACT_TYPE_CHOICES: [string, string][] = [
  ["full_time", "Полная занятость"],
  ["part_time", "Частичная занятость"],
  ["gph", "ГПХ"],
];

const getContractTypeLabel = (type: string): string => {
  const choice = CONTRACT_TYPE_CHOICES.find(([key]) => key === type);
  return choice ? choice[1] : "Не указан";
};

interface StaffHeaderProps {
  staffData: StaffData;
  handleDownloadExcel: () => void;
  handleDownloadZip: () => void;
  setShowAbsenceModal: (show: boolean) => void;
  hasAbsenceWithReason: boolean;
  staffPin?: string;
  onOpenAvatarFromFile?: () => void;
  onOpenAvatarFromCamera?: () => void;
  avatarUploadBusy?: boolean;
  avatarActionMessage?: string | null;
  faceSetupAnglesDone?: number;
  faceSetupAnglesLoading?: boolean;
}

const StaffHeader: React.FC<StaffHeaderProps> = ({
  staffData,
  handleDownloadExcel,
  handleDownloadZip,
  setShowAbsenceModal,
  hasAbsenceWithReason,
  staffPin,
  onOpenAvatarFromFile,
  onOpenAvatarFromCamera,
  avatarUploadBusy = false,
  avatarActionMessage = null,
  faceSetupAnglesDone = 0,
  faceSetupAnglesLoading = false,
}) => {
  const faceLabHref =
    staffPin && staffPin.length > 0
      ? `/face-lab?bootstrap=1&pin=${encodeURIComponent(staffPin)}`
      : "/face-lab?bootstrap=1";

  const avatarSrc = `${apiUrl}${staffData.avatar}`;
  const avatarAlt = `${staffData.surname} ${staffData.name}`;

  const showPhotoHub =
    Boolean(staffPin) &&
    Boolean(onOpenAvatarFromFile) &&
    Boolean(onOpenAvatarFromCamera);

  return (
    <div className="border-b border-gray-200 dark:border-gray-800">
      {/* Мобильная версия */}
      <div className="sm:hidden p-4 space-y-4">
        <div className="flex items-start gap-4">
          {showPhotoHub ? (
            <ProfileAvatarWithPhotoMenu
              avatarSrc={avatarSrc}
              avatarAlt={avatarAlt}
              sizeClassName="h-20 w-20"
              uploadBusy={avatarUploadBusy}
              onPickFile={() => onOpenAvatarFromFile?.()}
              onOpenCamera={() => onOpenAvatarFromCamera?.()}
            />
          ) : (
            <div className="h-20 w-20 shrink-0 overflow-hidden rounded-full border-2 border-primary-200 shadow-lg dark:border-primary-800">
              <img
                src={avatarSrc}
                alt={avatarAlt}
                className="h-full w-full object-cover"
              />
            </div>
          )}
          <div className="min-w-0 flex-1 pt-0.5">
            <h2 className="truncate text-xl font-bold text-gray-800 dark:text-gray-100">
              {staffData.surname} {staffData.name}
            </h2>
            {staffData.department && (
              <p className="mt-1 truncate text-sm text-gray-600 dark:text-gray-400">
                {formatDepartmentName(staffData.department)}
              </p>
            )}
          </div>
        </div>

        {staffPin ? (
          <ProfileFaceSetupCard
            href={faceLabHref}
            anglesDone={faceSetupAnglesDone}
            loading={faceSetupAnglesLoading}
          />
        ) : null}

        {avatarActionMessage ? (
          <p
            className={`text-sm ${
              avatarActionMessage.includes("Не удалось") ||
              avatarActionMessage.includes("ошибк")
                ? "text-red-600 dark:text-red-400"
                : "text-emerald-700 dark:text-emerald-300"
            }`}
            role="status"
          >
            {avatarActionMessage}
          </p>
        ) : null}

        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-gray-200/80 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-950/90">
            <p className="mb-1 text-xs text-gray-500 dark:text-gray-400">
              Должность
            </p>
            <p className="line-clamp-2 text-sm font-medium text-gray-800 dark:text-gray-200">
              {staffData.positions[0] || "Не указано"}
            </p>
          </div>
          <div className="rounded-lg border border-gray-200/80 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-950/90">
            <p className="mb-1 text-xs text-gray-500 dark:text-gray-400">
              Тип занятости
            </p>
            <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
              {getContractTypeLabel(staffData.contract_type || "")}
            </p>
          </div>
          <div className="col-span-2 rounded-lg bg-primary-50 p-3 dark:bg-primary-900/20">
            <p className="mb-1 text-xs text-primary-600 dark:text-primary-400">
              Процент за период
            </p>
            <p className="text-lg font-bold text-primary-700 dark:text-primary-300">
              {staffData.percent_for_period}%
            </p>
          </div>
        </div>
      </div>

      {/* Десктоп */}
      <div className="hidden sm:block">
        <div className="p-5 lg:p-6">
          <div className="flex items-start justify-between gap-4 lg:gap-6">
            <div className="flex min-w-0 flex-1 items-start gap-4 lg:gap-5">
              {showPhotoHub ? (
                <ProfileAvatarWithPhotoMenu
                  avatarSrc={avatarSrc}
                  avatarAlt={avatarAlt}
                  uploadBusy={avatarUploadBusy}
                  onPickFile={() => onOpenAvatarFromFile?.()}
                  onOpenCamera={() => onOpenAvatarFromCamera?.()}
                />
              ) : (
                <div className="h-20 w-20 shrink-0 overflow-hidden rounded-full border-2 border-primary-200 shadow-lg dark:border-primary-800 lg:h-24 lg:w-24">
                  <img
                    src={avatarSrc}
                    alt={avatarAlt}
                    className="h-full w-full object-cover"
                  />
                </div>
              )}

              <div className="min-w-0 flex-1 space-y-3">
                <div>
                  <h2 className="text-xl font-bold leading-tight text-gray-800 dark:text-gray-100 lg:text-2xl">
                    {staffData.surname} {staffData.name}
                  </h2>
                  {staffData.department && (
                    <p className="mt-1 text-sm leading-relaxed text-gray-500 dark:text-gray-400 lg:text-base">
                      {formatDepartmentName(staffData.department)}
                    </p>
                  )}
                </div>

                {staffPin ? (
                  <ProfileFaceSetupCard
                    href={faceLabHref}
                    anglesDone={faceSetupAnglesDone}
                    loading={faceSetupAnglesLoading}
                  />
                ) : null}

                {avatarActionMessage ? (
                  <p
                    className={`text-sm ${
                      avatarActionMessage.includes("Не удалось") ||
                      avatarActionMessage.includes("ошибк")
                        ? "text-red-600 dark:text-red-400"
                        : "text-emerald-700 dark:text-emerald-300"
                    }`}
                    role="status"
                  >
                    {avatarActionMessage}
                  </p>
                ) : null}

                <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs lg:text-sm">
                  <div className="flex items-center gap-1.5">
                    <span className="text-gray-500 dark:text-gray-400">
                      Должность:
                    </span>
                    <span className="font-medium text-gray-700 dark:text-gray-300">
                      {staffData.positions[0] || "Не указано"}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-gray-500 dark:text-gray-400">
                      Тип занятости:
                    </span>
                    <span className="font-medium text-gray-700 dark:text-gray-300">
                      {getContractTypeLabel(staffData.contract_type || "")}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-gray-500 dark:text-gray-400">
                      Процент за период:
                    </span>
                    <span className="font-semibold text-primary-600 dark:text-primary-400">
                      {staffData.percent_for_period}%
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-2 lg:gap-3">
              <ActionButton
                icon={<FaFileExcel size={16} />}
                label="Excel"
                onClick={handleDownloadExcel}
                variant="excel"
              />
              {hasAbsenceWithReason && (
                <ActionButton
                  icon={<FaArchive size={16} />}
                  label="ZIP"
                  onClick={handleDownloadZip}
                  variant="zip"
                />
              )}
              <ActionButton
                icon={<BsPlusLg size={16} />}
                label="Отсутствие"
                onClick={() => setShowAbsenceModal(true)}
                variant="absence"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StaffHeader;
