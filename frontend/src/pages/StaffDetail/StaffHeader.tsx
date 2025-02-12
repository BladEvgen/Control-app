import React, { useState } from "react";
import { FaChevronLeft, FaArchive } from "react-icons/fa";
import { BsFileEarmarkTextFill, BsPlusLg } from "react-icons/bs";
import { formatDepartmentName } from "../../utils/utils";
import { apiUrl } from "../../../apiConfig";
import { StaffData } from "../../schemas/IData";
import { motion, AnimatePresence } from "framer-motion";

interface IconButtonWithTooltipProps {
  icon: React.ReactNode;
  tooltip: string;
  onClick: () => void;
  extraClasses?: string;
}
const IconButtonWithTooltip: React.FC<IconButtonWithTooltipProps> = ({
  icon,
  tooltip,
  onClick,
  extraClasses = "",
}) => {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <div className="relative flex flex-col items-center">
      <motion.button
        onClick={onClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={`flex items-center justify-center w-12 h-12 rounded-lg shadow-lg transition-all focus:outline-none ${extraClasses}`}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
      >
        {icon}
      </motion.button>
      <AnimatePresence>
        {isHovered && (
          <motion.div
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: -10 }}
            exit={{ opacity: 0, y: -5 }}
            className="absolute bottom-full mb-2 px-2 py-1 bg-gray-900 text-white dark:bg-white dark:text-black text-xs rounded break-words max-w-xs z-10"
          >
            {tooltip}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

const BackButton: React.FC<{ onClick: () => void; tooltip: string }> = ({
  onClick,
  tooltip,
}) => {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <div className="relative flex flex-col items-center">
      <button
        onClick={onClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className="flex items-center justify-center w-12 h-12 bg-transparent text-green-500 dark:text-green-400 focus:outline-none rounded-full transition-all duration-300 ease-in-out hover:bg-green-100 dark:hover:bg-green-800"
      >
        <FaChevronLeft
          size={24}
          className={`transition-transform duration-300 ease-in-out ${
            isHovered ? "animate-wiggle" : ""
          }`}
        />
      </button>
      {isHovered && (
        <div className="absolute bottom-full mb-2 px-2 py-1 bg-gray-900 text-white text-xs rounded break-words max-w-xs z-10 transition-opacity duration-200">
          {tooltip}
        </div>
      )}
    </div>
  );
};

interface StaffHeaderProps {
  staffData: StaffData;
  navigateToChildDepartment: () => void;
  handleDownloadExcel: () => void;
  handleDownloadZip: () => void;
  setShowAbsenceModal: (show: boolean) => void;
  hasAbsenceWithReason: boolean;
}

const StaffHeader: React.FC<StaffHeaderProps> = ({
  staffData,
  navigateToChildDepartment,
  handleDownloadExcel,
  handleDownloadZip,
  setShowAbsenceModal,
  hasAbsenceWithReason,
}) => {
  return (
    <div className="flex flex-col sm:flex-row items-center justify-between p-8 border-b border-gray-200 dark:border-gray-700">
      <div className="flex items-center space-x-6">
        {/* Кнопка "Назад" */}
        <div className="hidden sm:block portrait:hidden landscape:flex">
          <BackButton onClick={navigateToChildDepartment} tooltip="Назад" />
        </div>
        <div className="w-28 h-28 rounded-full overflow-hidden shadow-xl">
          <img
            src={`${apiUrl}${staffData.avatar}`}
            alt="Avatar"
            className="object-cover w-full h-full"
          />
        </div>
        <div>
          <h2 className="text-4xl font-bold text-gray-800 dark:text-gray-100">
            {staffData.surname} {staffData.name}
          </h2>
          {staffData.department && (
            <p className="text-lg text-gray-500 dark:text-gray-400">
              {formatDepartmentName(staffData.department)}
            </p>
          )}
        </div>
      </div>
      {/* Группа кнопок для десктопа */}
      <div className="hidden sm:flex portrait:hidden landscape:flex items-center space-x-4">
        <IconButtonWithTooltip
          onClick={handleDownloadExcel}
          tooltip="Скачать Excel"
          icon={<BsFileEarmarkTextFill size={24} />}
          extraClasses="bg-gradient-to-r from-green-400 to-green-600 dark:from-green-500 dark:to-green-700 hover:from-green-500 hover:to-green-700 dark:hover:from-green-600 dark:hover:to-green-800"
        />
        {hasAbsenceWithReason && (
          <IconButtonWithTooltip
            onClick={handleDownloadZip}
            tooltip="Скачать ZIP"
            icon={<FaArchive size={24} />}
            extraClasses="bg-gradient-to-r from-orange-400 to-orange-600 dark:from-orange-500 dark:to-orange-700 hover:from-orange-500 hover:to-orange-700 dark:hover:from-orange-600 dark:hover:to-orange-800"
          />
        )}
        <IconButtonWithTooltip
          onClick={() => setShowAbsenceModal(true)}
          tooltip="Добавить отсутствие"
          icon={<BsPlusLg size={24} />}
          extraClasses="bg-gradient-to-r from-blue-500 to-blue-700 dark:from-blue-600 dark:to-blue-800 hover:from-blue-600 hover:to-blue-800 dark:hover:from-blue-700 dark:hover:to-blue-900"
        />
      </div>
    </div>
  );
};

export default StaffHeader;
