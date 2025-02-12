import React, { useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
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

type TooltipPosition = "top" | "left";

interface IconButtonWithTooltipProps {
  icon: React.ReactNode;
  tooltip: string;
  onClick: () => void;
  extraClasses?: string;
  tooltipPosition?: TooltipPosition;
}

const IconButtonWithTooltip: React.FC<IconButtonWithTooltipProps> = ({
  icon,
  tooltip,
  onClick,
  extraClasses = "",
  tooltipPosition = "top",
}) => {
  const [isHovered, setIsHovered] = useState(false);

  const tooltipAnimation =
    tooltipPosition === "left"
      ? {
          initial: { opacity: 0, x: 5 },
          animate: { opacity: 1, x: 0 },
          exit: { opacity: 0, x: 5 },
        }
      : {
          initial: { opacity: 0, y: -5 },
          animate: { opacity: 1, y: 0 },
          exit: { opacity: 0, y: -5 },
        };
  const tooltipClass =
    tooltipPosition === "left"
      ? "absolute right-full mr-2 top-1/4 transform -translate-y-1/2 px-2 py-1 bg-gray-900 text-white dark:bg-white dark:text-black text-xs rounded whitespace-nowrap"
      : "absolute bottom-full mb-4 left-0 px-2 py-1 bg-gray-900 text-white dark:bg-white dark:text-black text-xs rounded whitespace-nowrap";

  return (
    <div className="relative flex flex-col items-center">
      <motion.button
        onClick={onClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onFocus={() => setIsHovered(true)}
        onBlur={() => setIsHovered(false)}
        onTouchStart={() => setIsHovered(true)}
        onTouchEnd={() => setIsHovered(false)}
        variants={buttonVariants}
        whileHover="hover"
        whileTap="tap"
        className={`flex items-center justify-center w-12 h-12 rounded-full shadow-lg text-white transition-all focus:outline-none ${extraClasses}`}
      >
        {icon}
      </motion.button>
      <AnimatePresence>
        {isHovered && (
          <motion.div
            initial={tooltipAnimation.initial}
            animate={tooltipAnimation.animate}
            exit={tooltipAnimation.exit}
            className={tooltipClass}
          >
            {tooltip}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

const MobileActionButtons: React.FC<MobileActionButtonsProps> = ({
  navigateToChildDepartment = () => {},
  setShowAbsenceModal = () => {},
  handleDownloadExcel = () => {},
  handleDownloadZip = () => {},
  hasAbsenceWithReason = false,
}) => {
  const mobileButtonClasses = `
    fixed bottom-4 left-4 right-4 z-50 flex justify-between items-center
    portrait:flex sm:landscape:hidden md:landscape:hidden lg:landscape:hidden
  `;

  return createPortal(
    <>
      <div className={mobileButtonClasses}>
        <IconButtonWithTooltip
          onClick={navigateToChildDepartment}
          tooltip="Назад"
          icon={<FaChevronLeft size={24} />}
          extraClasses="bg-gradient-to-r from-green-400 to-green-600 dark:from-green-500 dark:to-green-700 hover:from-green-500 hover:to-green-700 dark:hover:from-green-600 dark:hover:to-green-800"
        />
        <IconButtonWithTooltip
          onClick={() => setShowAbsenceModal(true)}
          tooltip="Добавить отсутствие"
          icon={<BsPlusLg size={24} />}
          extraClasses="bg-gradient-to-r from-blue-500 to-blue-700 dark:from-blue-600 dark:to-blue-800 hover:from-blue-600 hover:to-blue-800 dark:hover:from-blue-700 dark:hover:to-blue-900 text-black dark:text-white"
        />
        <IconButtonWithTooltip
          onClick={handleDownloadExcel}
          tooltip="Скачать Excel"
          icon={<BsFileEarmarkTextFill size={24} />}
          tooltipPosition="left"
          extraClasses="bg-gradient-to-r from-green-400 to-green-600 dark:from-green-500 dark:to-green-700 hover:from-green-500 hover:to-green-700 dark:hover:from-green-600 dark:hover:to-green-800 text-black dark:text-white"
        />
      </div>

      {hasAbsenceWithReason && (
        <div className="fixed bottom-20 right-4 z-50 portrait:flex sm:landscape:hidden md:landscape:hidden lg:landscape:hidden">
          <IconButtonWithTooltip
            onClick={handleDownloadZip}
            tooltip="Скачать ZIP"
            icon={<FaArchive size={24} />}
            tooltipPosition="left"
            extraClasses="bg-gradient-to-r from-orange-400 to-orange-600 dark:from-orange-500 dark:to-orange-700 hover:from-orange-500 hover:to-orange-700 dark:hover:from-orange-600 dark:hover:to-orange-800 text-black dark:text-white"
          />
        </div>
      )}
    </>,
    document.body
  );
};

export default MobileActionButtons;
