import React from "react";
import { motion } from "framer-motion";

const getButtonStyles = (variant: string, disabled: boolean = false) => {
  const baseStyles =
    "inline-flex items-center justify-center px-5 py-2.5 rounded-lg font-medium shadow-sm transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-offset-2";

  const variantStyles = {
    home: `
      ${disabled ? "opacity-60" : ""}
      bg-gradient-to-r from-secondary-600 to-secondary-700
      hover:from-secondary-700 hover:to-secondary-800
      active:from-secondary-800 active:to-secondary-900
      text-white
      focus:ring-secondary-500
    `,
    back: `
      ${disabled ? "opacity-60" : ""}
      bg-gradient-to-r from-primary-600 to-primary-700
      hover:from-primary-700 hover:to-primary-800
      active:from-primary-800 active:to-primary-900
      text-white
      focus:ring-primary-500
    `,
    download: `
      ${disabled ? "opacity-60" : ""}
      bg-gradient-to-r from-success-500 to-success-600
      hover:from-success-600 hover:to-success-700
      active:from-success-700 active:to-success-800
      text-white
      focus:ring-success-500
    `,
    danger: `
      ${disabled ? "opacity-60" : ""}
      bg-gradient-to-r from-danger-500 to-danger-600
      hover:from-danger-600 hover:to-danger-700
      active:from-danger-700 active:to-danger-800
      text-white
      focus:ring-danger-500
    `,
  };

  return `${baseStyles} ${
    variantStyles[variant as keyof typeof variantStyles]
  }`;
};

export interface ModernButtonProps {
  variant: "home" | "back" | "download" | "danger";
  children: React.ReactNode;
  icon?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
  className?: string;
  type?: "button" | "submit" | "reset";
}

const ModernButton: React.FC<ModernButtonProps> = ({
  variant,
  children,
  icon,
  onClick,
  disabled = false,
  loading = false,
  className = "",
  type = "button",
}) => {
  return (
    <motion.button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      className={`${getButtonStyles(
        variant,
        disabled || loading
      )} ${className}`}
      whileHover={disabled || loading ? {} : { scale: 1.03 }}
      whileTap={disabled || loading ? {} : { scale: 0.97 }}
      transition={{ duration: 0.2 }}
    >
      {loading ? (
        <>
          <svg
            className="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            ></circle>
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            ></path>
          </svg>
          <span>{children}</span>
        </>
      ) : (
        <>
          {icon && <span className="mr-2">{icon}</span>}
          <span>{children}</span>
        </>
      )}
    </motion.button>
  );
};

export default ModernButton;
