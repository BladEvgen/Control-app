import React from "react";
import { motion } from "framer-motion";

interface WaitNotificationProps {
  message?: string;
}

const WaitNotification: React.FC<WaitNotificationProps> = ({ message }) => {
  const displayMessage =
    message ||
    "Загрузка может занять некоторое время, пожалуйста, подождите...";

  return (
    <motion.div
      animate={{ opacity: [1, 0.2, 1] }}
      transition={{
        duration: 2,
        repeat: Infinity,
        repeatType: "loop",
        ease: "easeInOut",
      }}
      className="
        mt-2 p-4 border-l-4 border-yellow-500 
        bg-yellow-100 text-yellow-800 text-sm 
        rounded-md shadow-md 
        dark:bg-yellow-900 dark:text-yellow-300
      "
    >
      {displayMessage}
    </motion.div>
  );
};

export default WaitNotification;
