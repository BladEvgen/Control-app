import React from "react";
import { Link } from "../RouterUtils";
import { FaHome } from "react-icons/fa";

interface NotificationProps {
  message: string;
  type: "warning" | "error";
  link?: string;
  linkText?: string;
}

const Notification: React.FC<NotificationProps> = ({
  message,
  type,
  link,
  linkText,
}) => {
  const bgColor =
    type === "warning"
      ? "bg-yellow-100 dark:bg-yellow-900"
      : "bg-red-100 dark:bg-red-900";
  const borderColor =
    type === "warning" ? "border-yellow-500" : "border-red-500";
  const textColor =
    type === "warning"
      ? "text-yellow-700 dark:text-yellow-300"
      : "text-red-700 dark:text-red-300";

  const animationClass = type === "warning" ? "animate-bounce" : "animate-once";

  return (
    <div className="flex flex-col justify-center items-center h-screen px-4">
      <div
        className={`${bgColor} ${borderColor} ${textColor} px-8 py-6 rounded-lg shadow-lg transition transform duration-500 ease-in-out ${animationClass} max-w-lg w-full mx-auto`}
        role="alert"
      >
        <p className="font-bold text-xl md:text-2xl">
          {type === "warning" ? "Предупреждение!" : "Ошибка!"}
        </p>
        <p className="text-lg md:text-xl">{message}</p>
        {link && (
          <Link
            to={link}
            className="mt-6 bg-gray-800 text-white px-6 py-3 rounded-lg shadow-md hover:bg-gray-900 transition transform hover:-translate-y-1 hover:scale-105 flex items-center justify-center"
          >
            <FaHome className="mr-2" />
            {linkText ? linkText : "Вернуться на главную"}
          </Link>
        )}
      </div>
    </div>
  );
};

export default Notification;
