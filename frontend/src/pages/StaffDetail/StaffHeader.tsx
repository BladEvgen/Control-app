import React from "react";
import { FaArchive, FaFileExcel } from "react-icons/fa";
import { BsPlusLg } from "react-icons/bs";
import { formatDepartmentName } from "../../utils/utils";
import { apiUrl } from "../../../apiConfig";
import { StaffData } from "../../schemas/IData";
import { ProfileAvatarWithPhotoMenu } from "./StaffProfilePhotoHub";

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

const contractLabels: Record<string, string> = {
  full_time: "Полная занятость",
  part_time: "Частичная занятость",
  gph: "ГПХ",
};

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
}) => {
  const avatarSrc = `${apiUrl}${staffData.avatar}`;
  const avatarAlt = `${staffData.surname} ${staffData.name}`;
  const showPhotoHub = Boolean(
    staffPin && onOpenAvatarFromFile && onOpenAvatarFromCamera,
  );
  return (
    <section className="staff-profile-header">
      <div className="staff-profile-top">
        <div className="staff-profile-identity">
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
            <img
              src={avatarSrc}
              alt={avatarAlt}
              className="h-20 w-20 shrink-0 rounded-full object-cover"
            />
          )}
          <div className="min-w-0">
            <h1 className="text-xl font-semibold break-words sm:text-2xl">
              {avatarAlt}
            </h1>
            {staffData.department && (
              <p className="mt-1 text-sm text-gray-600 dark:text-gray-300 break-words">
                {formatDepartmentName(staffData.department)}
              </p>
            )}
          </div>
        </div>
        <div className="staff-profile-actions">
          <button
            type="button"
            className="ws-btn-primary"
            onClick={handleDownloadExcel}
          >
            <FaFileExcel aria-hidden />
            Скачать Excel
          </button>
          {hasAbsenceWithReason && (
            <button
              type="button"
              className="ws-btn-ghost"
              onClick={handleDownloadZip}
            >
              <FaArchive aria-hidden />
              Документы ZIP
            </button>
          )}
          <button
            type="button"
            className="ws-btn-ghost"
            onClick={() => setShowAbsenceModal(true)}
          >
            <BsPlusLg aria-hidden />
            Отсутствие
          </button>
        </div>
      </div>
      <dl className="staff-profile-facts">
        <div>
          <dt>Должность</dt>
          <dd>{staffData.positions.join(", ") || "Не указана"}</dd>
        </div>
        <div>
          <dt>Занятость</dt>
          <dd>
            {contractLabels[staffData.contract_type || ""] || "Не указана"}
          </dd>
        </div>
        <div>
          <dt>Посещаемость за период</dt>
          <dd>{staffData.percent_for_period}%</dd>
        </div>
      </dl>
      {avatarActionMessage && (
        <p className="text-sm" role="status">
          {avatarActionMessage}
        </p>
      )}
    </section>
  );
};
export default StaffHeader;
