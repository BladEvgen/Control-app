import React, { useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { FaArchive } from "react-icons/fa";
import { BsFileEarmarkTextFill, BsPlusLg } from "react-icons/bs";

interface MobileActionButtonsProps {
  setShowAbsenceModal: (show: boolean) => void;
  handleDownloadExcel: () => void;
  handleDownloadZip: () => void;
  hasAbsenceWithReason: boolean;
}

const MobileActionButtons: React.FC<MobileActionButtonsProps> = ({
  setShowAbsenceModal,
  handleDownloadExcel,
  handleDownloadZip,
  hasAbsenceWithReason,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const buttons = [
    {
      id: "excel",
      icon: <BsFileEarmarkTextFill size={20} />,
      label: "Excel",
      onClick: handleDownloadExcel,
      color: "from-green-500 to-green-600",
      darkColor: "dark:from-green-600 dark:to-green-700",
    },
    ...(hasAbsenceWithReason
      ? [
          {
            id: "zip",
            icon: <FaArchive size={20} />,
            label: "ZIP",
            onClick: handleDownloadZip,
            color: "from-orange-500 to-orange-600",
            darkColor: "dark:from-orange-600 dark:to-orange-700",
          },
        ]
      : []),
    {
      id: "absence",
      icon: <BsPlusLg size={20} />,
      label: "Отсутствие",
      onClick: () => setShowAbsenceModal(true),
      color: "from-blue-500 to-blue-600",
      darkColor: "dark:from-blue-600 dark:to-blue-700",
    },
  ];

  return createPortal(
    <div className="fixed bottom-20 md:bottom-24 left-4 md:left-6 z-50 block sm:hidden">
      <div className="flex flex-col items-center gap-3">
        <AnimatePresence>
          {isExpanded && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center gap-3"
            >
              {buttons.map((button, index) => (
                <motion.button
                  key={button.id}
                  initial={{ opacity: 0, y: 20, scale: 0.8 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 20, scale: 0.8 }}
                  transition={{ delay: index * 0.05 }}
                  onClick={() => {
                    button.onClick();
                    setIsExpanded(false);
                  }}
                  className={`
                    flex items-center justify-center gap-2
                    w-14 h-14 rounded-full shadow-xl
                    bg-gradient-to-r ${button.color} ${button.darkColor}
                    text-white font-medium
                    transition-all duration-200
                    hover:shadow-2xl hover:scale-110 active:scale-95
                    ring-2 ring-white/20 dark:ring-gray-800/50
                  `}
                  title={button.label}
                  aria-label={button.label}
                >
                  {button.icon}
                </motion.button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Главная кнопка */}
        <motion.button
          onClick={() => setIsExpanded(!isExpanded)}
          className={`
            flex items-center justify-center
            w-12 h-12 rounded-full shadow-xl
            bg-gradient-to-r from-rose-600 to-rose-700
            dark:from-rose-700 dark:to-rose-800
            text-white
            transition-all duration-300
            hover:shadow-2xl hover:scale-105 active:scale-95
            border-2 border-white/20 dark:border-gray-800/50 backdrop-blur-sm
          `}
          style={{
            marginBottom: "env(safe-area-inset-bottom, 0px)",
          }}
          whileTap={{ scale: 0.9 }}
          animate={{ rotate: isExpanded ? 45 : 0 }}
          transition={{ duration: 0.2 }}
          aria-label={isExpanded ? "Закрыть меню" : "Открыть меню действий"}
          aria-expanded={isExpanded}
        >
          <BsPlusLg size={20} />
        </motion.button>
      </div>
    </div>,
    document.body
  );
};

export default MobileActionButtons;
