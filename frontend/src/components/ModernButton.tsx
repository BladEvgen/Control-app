import React from "react";

const modernButtonBase = `
  inline-flex items-center justify-center
  px-6 py-3
  rounded-full
  font-semibold
  text-white
  shadow-lg
  transition-all duration-300
  focus:outline-none focus:ring-2 focus:ring-offset-2
`;

const colorVariants = {
  home: `
    bg-gradient-to-r from-purple-500 to-purple-600
    hover:from-purple-600 hover:to-purple-700
    focus:ring-purple-400
  `,
  back: `
    bg-gradient-to-r from-blue-500 to-blue-600
    hover:from-blue-600 hover:to-blue-700
    focus:ring-blue-400
  `,
  download: `
    bg-gradient-to-r from-green-500 to-green-600
    hover:from-green-600 hover:to-green-700
    focus:ring-green-400
  `,
};

export interface ModernButtonProps {
  variant: "home" | "back" | "download";
  children: React.ReactNode;
  icon?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
  className?: string;
}

const ModernButton: React.FC<ModernButtonProps> = ({
  variant,
  children,
  icon,
  onClick,
  disabled = false,
  loading = false,
  className = "",
}) => {
  const baseClasses =
    modernButtonBase +
    (disabled || loading
      ? " opacity-70 cursor-not-allowed"
      : " transform hover:-translate-y-1 hover:scale-105");

  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={`
        ${baseClasses}
        ${colorVariants[variant]}
        ${className}
      `}
    >
      {loading && (
        <svg
          className="animate-spin h-5 w-5 mr-2"
          viewBox="0 0 24 24"
          fill="none"
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
      )}
      {icon && !loading && <span className="mr-2">{icon}</span>}
      {children}
    </button>
  );
};

export default ModernButton;
