import React from "react";
import { motion } from "framer-motion";
import { FaChevronLeft, FaArchive } from "react-icons/fa";
import { BsFileEarmarkTextFill, BsPlusLg } from "react-icons/bs";
import { formatDepartmentName } from "../../utils/utils";
import { apiUrl } from "../../../apiConfig";
import { StaffData } from "../../schemas/IData";

const buttonVariants = {
  hover: { scale: 1.1, transition: { duration: 0.2 } },
  tap: { scale: 0.95, transition: { duration: 0.1 } },
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
        <motion.button
          variants={buttonVariants}
          whileHover="hover"
          whileTap="tap"
          onClick={navigateToChildDepartment}
          className="hidden sm:block text-green-500 hover:text-green-600 focus:outline-none"
        >
          <FaChevronLeft size={28} />
        </motion.button>
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
      <div className="flex items-center space-x-4">
        <motion.button
          variants={buttonVariants}
          whileHover="hover"
          whileTap="tap"
          onClick={handleDownloadExcel}
          className="hidden sm:flex items-center bg-green-600 hover:bg-green-700 text-white px-6 py-3 rounded-lg shadow transition-colors focus:outline-none"
        >
          <BsFileEarmarkTextFill className="mr-3" size={24} />
          Скачать Excel
        </motion.button>
        {hasAbsenceWithReason && (
          <motion.button
            variants={buttonVariants}
            whileHover="hover"
            whileTap="tap"
            onClick={handleDownloadZip}
            className="hidden sm:flex items-center bg-orange-600 hover:bg-orange-700 text-white px-6 py-3 rounded-lg shadow transition-colors focus:outline-none"
          >
            <FaArchive className="mr-3" size={24} />
            Скачать ZIP
          </motion.button>
        )}
        <motion.button
          variants={buttonVariants}
          whileHover="hover"
          whileTap="tap"
          onClick={() => setShowAbsenceModal(true)}
          className="hidden sm:flex items-center bg-gradient-to-r from-blue-900 to-blue-600 text-white px-6 py-3 rounded-lg shadow transition-colors focus:outline-none"
        >
          <BsPlusLg className="mr-3" size={24} />
          Добавить отсутствие
        </motion.button>
      </div>
    </div>
  );
};

export default StaffHeader;
