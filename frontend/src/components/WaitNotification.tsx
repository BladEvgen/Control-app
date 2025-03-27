import React from "react";
import { motion } from "framer-motion";
import { FaHourglassHalf } from "react-icons/fa";

interface WaitNotificationProps {
  message?: string;
}

const WaitNotification: React.FC<WaitNotificationProps> = ({ message }) => {
  const displayMessage =
    message ||
    "Загрузка может занять некоторое время, пожалуйста, подождите...";

  return (
    <motion.div
      className="relative overflow-hidden bg-gradient-to-r from-warning-50 to-warning-100 dark:from-warning-900/30 dark:to-warning-800/40 border-l-4 border-warning-500 dark:border-warning-600 rounded-lg shadow-md"
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="px-4 py-3 flex items-center">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{
            duration: 2,
            repeat: Infinity,
            ease: "linear",
          }}
          className="mr-3 text-warning-600 dark:text-warning-400 flex-shrink-0"
        >
          <FaHourglassHalf size={20} />
        </motion.div>

        <div className="flex-1">
          <motion.p
            className="text-sm font-medium text-warning-800 dark:text-warning-200 text-text-dark"
            animate={{ opacity: [1, 0.6, 1] }}
            transition={{
              duration: 2,
              repeat: Infinity,
              repeatType: "loop",
              ease: "easeInOut",
            }}
          >
            {displayMessage}
          </motion.p>
        </div>
      </div>

      {/* Progress bar */}
      <motion.div
        className="absolute bottom-0 left-0 h-1 bg-warning-500 dark:bg-warning-600"
        initial={{ width: "0%" }}
        animate={{ width: "100%" }}
        transition={{
          duration: 10,
          ease: "linear",
          repeat: Infinity,
        }}
      />
    </motion.div>
  );
};

export default WaitNotification;
