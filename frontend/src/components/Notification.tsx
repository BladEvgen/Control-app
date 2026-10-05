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

  return (
    <div className="my-4">
      <div
        className={`${bgColor} ${borderColor} ${textColor} border px-4 py-4 rounded-lg w-full`}
        role="alert"
      >
        <p className="font-semibold text-base">
          {type === "warning" ? "Предупреждение!" : "Ошибка!"}
        </p>
        <p className="mt-1 text-sm">{message}</p>
        {link && (
          <Link
            to={link}
            className="mt-3 min-h-11 underline underline-offset-4 inline-flex items-center"
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
