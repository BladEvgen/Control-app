import React from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { FaChevronLeft, FaArchive } from "react-icons/fa";
import { BsFileEarmarkTextFill, BsPlusLg } from "react-icons/bs";

const buttonVariants = {
  hover: { scale: 1.1, transition: { duration: 0.2 } },
  tap: { scale: 0.95, transition: { duration: 0.1 } },
};

interface MobileActionButtonsProps {
  navigateToChildDepartment: () => void;
  setShowAbsenceModal: (show: boolean) => void;
  handleDownloadExcel: () => void;
  handleDownloadZip: () => void;
  hasAbsenceWithReason: boolean;
}

const MobileActionButtons: React.FC<MobileActionButtonsProps> = ({
  navigateToChildDepartment,
  setShowAbsenceModal,
  handleDownloadExcel,
  handleDownloadZip,
  hasAbsenceWithReason,
}) => {
  const buttons = (
    <>
      <div className="sm:hidden fixed bottom-4 left-4 right-4 flex justify-between z-50">
        <motion.button
          variants={buttonVariants}
          whileHover="hover"
          whileTap="tap"
          onClick={navigateToChildDepartment}
          className="bg-green-500 hover:bg-green-600 text-white rounded-full p-4 shadow-lg focus:outline-none transition-transform"
        >
          <FaChevronLeft size={24} />
        </motion.button>
        <motion.button
          variants={buttonVariants}
          whileHover="hover"
          whileTap="tap"
          onClick={() => setShowAbsenceModal(true)}
          className="bg-gradient-to-r from-blue-900 to-blue-600 text-white rounded-full p-4 shadow-lg focus:outline-none transition-transform"
        >
          <BsPlusLg size={24} />
        </motion.button>
        <motion.button
          variants={buttonVariants}
          whileHover="hover"
          whileTap="tap"
          onClick={handleDownloadExcel}
          className="bg-green-600 hover:bg-green-700 text-white rounded-full p-4 shadow-lg focus:outline-none transition-transform"
        >
          <BsFileEarmarkTextFill size={24} />
        </motion.button>
      </div>

      {hasAbsenceWithReason && (
        <motion.button
          variants={buttonVariants}
          whileHover="hover"
          whileTap="tap"
          onClick={handleDownloadZip}
          className="sm:hidden fixed bottom-20 right-4 bg-orange-600 hover:bg-orange-700 text-white rounded-full p-4 shadow-lg z-50 focus:outline-none transition-transform"
        >
          <FaArchive size={24} />
        </motion.button>
      )}
    </>
  );

  return createPortal(buttons, document.body);
};

export default MobileActionButtons;
