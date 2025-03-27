import React, { FC } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { Link } from "../RouterUtils";

interface FloatingButtonProps {
  /** If provided, will render a <Link> instead of a <button>. */
  to?: string | number;
  /** Click handler, if to is not provided. */
  onClick?: () => void;
  /** Position: 'left' or 'right' at the bottom of the screen. Default is 'right'. */
  position?: "left" | "right";
  /** Icon to display inside the button. */
  icon: React.ReactNode;
  /** Render via portal (true) or inline (false). Default is true. */
  usePortal?: boolean;
  /** Color variant: 'home', 'back', or 'download'. */
  variant: "home" | "back" | "download";
}

const getButtonGradient = (variant: string) => {
  switch (variant) {
    case "home":
      return "bg-gradient-to-r from-secondary-600 to-secondary-700 hover:from-secondary-700 hover:to-secondary-800";
    case "back":
      return "bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-700 hover:to-primary-800";
    case "download":
      return "bg-gradient-to-r from-success-500 to-success-600 hover:from-success-600 hover:to-success-700";
    default:
      return "bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-700 hover:to-primary-800";
  }
};

const getRingColor = (variant: string) => {
  switch (variant) {
    case "home":
      return "focus:ring-secondary-500";
    case "back":
      return "focus:ring-primary-500";
    case "download":
      return "focus:ring-success-500";
    default:
      return "focus:ring-primary-500";
  }
};

export const FloatingButton: FC<FloatingButtonProps> = ({
  to,
  onClick,
  position = "right",
  icon,
  usePortal = true,
  variant,
}) => {
  const buttonVariants = {
    initial: { scale: 1, y: 0 },
    hover: { scale: 1.05, y: -3 },
    tap: { scale: 0.95 },
  };

  const buttonClassName = `
    fixed bottom-5 
    ${position === "right" ? "right-5" : "left-5"}
    z-50
    p-4
    rounded-full
    text-white
    shadow-lg
    md:hidden              
    focus:outline-none
    focus:ring-2
    focus:ring-offset-2
    ${getButtonGradient(variant)}
    ${getRingColor(variant)}
  `;

  const buttonContent = (
    <motion.button
      variants={buttonVariants}
      initial="initial"
      whileHover="hover"
      whileTap="tap"
      onClick={onClick}
      className={buttonClassName}
      aria-label={variant}
    >
      {icon}
    </motion.button>
  );

  const element = to ? <Link to={to}>{buttonContent}</Link> : buttonContent;

  return usePortal ? createPortal(element, document.body) : element;
};

export default FloatingButton;
