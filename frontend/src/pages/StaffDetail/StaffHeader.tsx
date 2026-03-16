import React from "react";
import { FaArchive, FaFileExcel } from "react-icons/fa";
import { BsPlusLg } from "react-icons/bs";
import { formatDepartmentName } from "../../utils/utils";
import { apiUrl } from "../../../apiConfig";
import { StaffData } from "../../schemas/IData";
import { motion } from "framer-motion";

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
}

const StaffHeader: React.FC<StaffHeaderProps> = ({
  staffData,
  handleDownloadExcel,
  handleDownloadZip,
  setShowAbsenceModal,
  hasAbsenceWithReason,
}) => {
  return (
    <div className="border-b border-gray-200 dark:border-gray-700">
      {/* Мобильная версия - компактная карточка */}
      <div className="sm:hidden p-4 space-y-4">
        {/* Аватарка и ФИО */}
        <div className="flex items-center space-x-4">
          <div className="w-20 h-20 rounded-full overflow-hidden shadow-lg flex-shrink-0 border-2 border-primary-200 dark:border-primary-800">
            <img
              src={`${apiUrl}${staffData.avatar}`}
              alt={`${staffData.surname} ${staffData.name}`}
              className="object-cover w-full h-full"
            />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-bold text-gray-800 dark:text-gray-100 truncate">
              {staffData.surname} {staffData.name}
            </h2>
            {staffData.department && (
              <p className="text-sm text-gray-600 dark:text-gray-400 truncate mt-1">
                {formatDepartmentName(staffData.department)}
              </p>
            )}
          </div>
        </div>

        {/* Информация в виде компактных меток */}
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
              Должность
            </p>
            <p className="text-sm font-medium text-gray-800 dark:text-gray-200 line-clamp-2">
              {staffData.positions[0] || "Не указано"}
            </p>
          </div>
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
              Тип занятости
            </p>
            <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
              {getContractTypeLabel(staffData.contract_type || "")}
            </p>
          </div>
          <div className="bg-primary-50 dark:bg-primary-900/20 rounded-lg p-3 col-span-2">
            <p className="text-xs text-primary-600 dark:text-primary-400 mb-1">
              Процент за период
            </p>
            <p className="text-lg font-bold text-primary-700 dark:text-primary-300">
              {staffData.percent_for_period}%
            </p>
          </div>
        </div>
      </div>

      {/* Десктопная версия - переработанный layout */}
      <div className="hidden sm:block">
        <div className="p-5 lg:p-6">
          <div className="flex items-start justify-between gap-4 lg:gap-6">
            {/* Левая часть - аватарка и основная информация */}
            <div className="flex items-start gap-4 lg:gap-5 flex-1 min-w-0">
              <div className="w-20 h-20 lg:w-24 lg:h-24 rounded-full overflow-hidden shadow-lg flex-shrink-0 border-2 border-primary-200 dark:border-primary-800">
                <img
                  src={`${apiUrl}${staffData.avatar}`}
                  alt={`${staffData.surname} ${staffData.name}`}
                  className="object-cover w-full h-full"
                />
              </div>
              <div className="flex-1 min-w-0 space-y-2">
                <div>
                  <h2 className="text-xl lg:text-2xl font-bold text-gray-800 dark:text-gray-100 leading-tight">
                    {staffData.surname} {staffData.name}
                  </h2>
                  {staffData.department && (
                    <p className="text-sm lg:text-base text-gray-500 dark:text-gray-400 mt-1 leading-relaxed">
                      {formatDepartmentName(staffData.department)}
                    </p>
                  )}
                </div>
                {/* Информация в компактном виде */}
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs lg:text-sm">
                  <div className="flex items-center gap-1.5">
                    <span className="text-gray-500 dark:text-gray-400">Должность:</span>
                    <span className="font-medium text-gray-700 dark:text-gray-300">
                      {staffData.positions[0] || "Не указано"}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-gray-500 dark:text-gray-400">Тип занятости:</span>
                    <span className="font-medium text-gray-700 dark:text-gray-300">
                      {getContractTypeLabel(staffData.contract_type || "")}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-gray-500 dark:text-gray-400">Процент за период:</span>
                    <span className="font-semibold text-primary-600 dark:text-primary-400">
                      {staffData.percent_for_period}%
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Правая часть - кнопки действий */}
            <div className="flex items-center gap-2 lg:gap-3 flex-shrink-0">
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
