import React, { FC } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { Link } from "../RouterUtils";

const buttonVariants = {
  hover: { scale: 1.05, transition: { duration: 0.2 } },
  tap: { scale: 0.9, transition: { duration: 0.1 } },
};

const floatingColorVariants = {
  home: `
    bg-gradient-to-r from-purple-500 to-purple-600
    hover:from-purple-600 hover:to-purple-700
    dark:from-purple-600 dark:to-purple-700
    focus:ring-purple-400
  `,
  back: `
    bg-gradient-to-r from-blue-500 to-blue-600
    hover:from-blue-600 hover:to-blue-700
    dark:from-blue-600 dark:to-blue-700
    focus:ring-blue-400
  `,
  download: `
    bg-gradient-to-r from-green-500 to-green-600
    hover:from-green-600 hover:to-green-700
    dark:from-green-600 dark:to-green-700
    focus:ring-green-400
  `,
};

export type FloatingButtonVariant = "home" | "back" | "download";

export interface FloatingButtonProps {
  /** Если указано, будет <Link> вместо <button>. */
  to?: string;
  /** Обработчик клика, если to не указано. */
  onClick?: () => void;
  /** Позиция кнопки: 'left' или 'right' внизу экрана. По умолчанию 'right'. */
  position?: "left" | "right";
  /** Иконка внутри кнопки. */
  icon: React.ReactNode;
  /** Рендер через портал (true) или инлайново (false). По умолчанию true. */
  usePortal?: boolean;
  /** Вариант цветовой схемы: 'home', 'back', или 'download'. */
  variant: FloatingButtonVariant;
}

export const FloatingButton: FC<FloatingButtonProps> = ({
  to,
  onClick,
  position = "right",
  icon,
  usePortal = true,
  variant,
}) => {
  const buttonContent = (
    <motion.button
      variants={buttonVariants}
      whileHover="hover"
      whileTap="tap"
      onClick={onClick}
      className={`
        fixed bottom-4
        ${position === "right" ? "right-4" : "left-4"}
        z-50
        p-4
        rounded-full
        text-white
        shadow-lg
        md:hidden              
        focus:outline-none
        focus:ring-2
        focus:ring-offset-2
        transform-gpu
        transition-all duration-300
        ${floatingColorVariants[variant]}
      `}
    >
      {icon}
    </motion.button>
  );

  const element = to ? <Link to={to}>{buttonContent}</Link> : buttonContent;

  return usePortal ? createPortal(element, document.body) : element;
};

export default FloatingButton;
