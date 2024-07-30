import React from "react";

interface NotificationProps {
  message: string;
  type: "warning" | "error";
}

const Notification: React.FC<NotificationProps> = ({ message, type }) => {
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
  const animationClass =
    type === "warning" ? "animate-bounce" : "animate-pulse";

  return (
    <div className="flex justify-center items-center h-screen px-4">
      <div
        className={`${bgColor} ${borderColor} ${textColor} px-8 py-6 rounded-lg shadow-lg transition transform duration-500 ease-in-out ${animationClass} max-w-lg w-full mx-auto`}
        role="alert"
      >
        <p className="font-bold text-xl md:text-2xl">
          {type === "warning" ? "Предупреждение!" : "Ошибка!"}
        </p>
        <p className="text-lg md:text-xl">{message}</p>
      </div>
    </div>
  );
};

export default Notification;
