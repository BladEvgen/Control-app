import React from "react";

export interface ModernButtonProps {
  variant: "home" | "back" | "download" | "danger" | "outline";
  children: React.ReactNode;
  icon?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
  className?: string;
  type?: "button" | "submit" | "reset";
}

const tones: Record<ModernButtonProps["variant"], string> = {
  home: "bg-gray-100 text-gray-900 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700",
  back: "bg-gray-100 text-gray-900 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700",
  download:
    "bg-primary-700 text-white hover:bg-primary-800 dark:bg-primary-600 dark:hover:bg-primary-700",
  danger: "bg-danger-700 text-white hover:bg-danger-800",
  outline:
    "border border-gray-300 bg-white text-gray-900 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 dark:hover:bg-gray-800",
};

export default function ModernButton({
  variant,
  children,
  icon,
  onClick,
  disabled = false,
  loading = false,
  className = "",
  type = "button",
}: ModernButtonProps) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      aria-busy={loading}
      className={`inline-flex min-h-11 items-center justify-center rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 ${tones[variant]} ${className}`}
    >
      {loading ? (
        <span
          className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
          aria-hidden
        />
      ) : (
        icon && (
          <span className="mr-2" aria-hidden>
            {icon}
          </span>
        )
      )}
      <span>{children}</span>
    </button>
  );
}
