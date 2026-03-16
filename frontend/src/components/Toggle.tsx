import { motion } from "framer-motion";
import { memo, useId } from "react";

const THUMB_OFFSET_PX = 20;

type ToggleVariant =
  | "default"
  | "purple"
  | "blue"
  | "rose"
  | "orange"
  | "green";

type Props = {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
  ariaLabel?: string;
  disabled?: boolean;
  id?: string;
  variant?: ToggleVariant;
  noBleed?: boolean;
  labelPosition?: "left" | "right";
  className?: string;
  labelClassName?: string;
};

function ToggleInner({
  checked,
  onChange,
  label,
  ariaLabel,
  disabled,
  id,
  variant = "default",
  noBleed = false,
  labelPosition = "right",
  className,
  labelClassName,
}: Props) {
  const autoId = useId();
  const inputId = id ?? autoId;

  const getVariantClasses = () => {
    switch (variant) {
      case "purple":
        return [
          "peer-checked:bg-gradient-to-r peer-checked:from-violet-500 peer-checked:to-indigo-500",
          "peer-checked:ring-violet-300/70 peer-checked:dark:ring-violet-300/25",
          "peer-checked:shadow-[0_8px_20px_rgba(139,92,246,0.35)]",
        ];
      case "blue":
        return [
          "peer-checked:bg-gradient-to-r peer-checked:from-sky-500 peer-checked:to-blue-600",
          "peer-checked:ring-sky-300/70 peer-checked:dark:ring-sky-300/25",
          "peer-checked:shadow-[0_8px_20px_rgba(59,130,246,0.35)]",
        ];
      case "rose":
        return [
          "peer-checked:bg-gradient-to-r peer-checked:from-rose-500 peer-checked:to-pink-600",
          "peer-checked:ring-rose-300/70 peer-checked:dark:ring-rose-300/25",
          "peer-checked:shadow-[0_8px_20px_rgba(244,63,94,0.35)]",
        ];
      case "orange":
        return [
          "peer-checked:bg-gradient-to-r peer-checked:from-amber-500 peer-checked:to-orange-500",
          "peer-checked:ring-amber-300/70 peer-checked:dark:ring-amber-300/25",
          "peer-checked:shadow-[0_8px_20px_rgba(251,146,60,0.35)]",
        ];
      case "green":
        return [
          "peer-checked:bg-gradient-to-r peer-checked:from-emerald-500 peer-checked:to-green-600",
          "peer-checked:ring-emerald-300/70 peer-checked:dark:ring-emerald-300/25",
          "peer-checked:shadow-[0_8px_20px_rgba(16,185,129,0.35)]",
        ];
      default:
        return [
          "peer-checked:bg-gradient-to-r peer-checked:from-sky-500 peer-checked:to-blue-600",
          "peer-checked:dark:from-violet-500 peer-checked:dark:to-indigo-500",
          "peer-checked:ring-sky-300/70 peer-checked:dark:ring-violet-300/40",
          "peer-checked:shadow-[0_8px_20px_rgba(59,130,246,0.35)] peer-checked:dark:shadow-[0_8px_20px_rgba(139,92,246,0.4)]",
        ];
    }
  };

  const getFocusRingClasses = () => {
    switch (variant) {
      case "blue":
        return "focus-within:ring-2 focus-within:ring-sky-400/60 focus-within:dark:ring-sky-300/40";
      case "rose":
        return "focus-within:ring-2 focus-within:ring-rose-400/60 focus-within:dark:ring-rose-300/40";
      case "orange":
        return "focus-within:ring-2 focus-within:ring-amber-400/60 focus-within:dark:ring-amber-300/40";
      case "green":
        return "focus-within:ring-2 focus-within:ring-emerald-400/60 focus-within:dark:ring-emerald-300/40";
      case "purple":
        return "focus-within:ring-2 focus-within:ring-violet-400/60 focus-within:dark:ring-violet-300/40";
      default:
        return "focus-within:ring-2 focus-within:ring-sky-400/60 focus-within:dark:ring-violet-400/50";
    }
  };

  const hitAreaClasses = noBleed ? "p-0 m-0" : "p-2 -m-2 sm:p-1 sm:-m-1";

  return (
    <label
      htmlFor={inputId}
      className={[
        "inline-flex items-center gap-3 select-none cursor-pointer rounded-lg",
        hitAreaClasses,
        disabled ? "opacity-60 cursor-not-allowed" : "",
        "transition-opacity duration-200",
        className ?? "",
      ].join(" ")}
    >
      <span
        className={[
          "relative inline-block",
          labelPosition === "left" ? "order-1" : checked ? "order-1" : "order-0",
        ].join(" ")}
      >
        <input
          id={inputId}
          type="checkbox"
          role="switch"
          aria-checked={checked}
          aria-label={ariaLabel ?? label ?? "Переключатель"}
          className="peer sr-only"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />

        <span
          className={[
            "block h-7 w-11 md:h-7 md:w-11 sm:h-6 sm:w-10 rounded-full transition-all duration-300 ease-out",
            "bg-slate-200/80 shadow-inner dark:bg-slate-700/80",
            "ring-1 ring-slate-300/70 dark:ring-black/30 border border-slate-200/70 dark:border-slate-600/70",
            ...getVariantClasses(),
          ].join(" ")}
        />

        <motion.span
          aria-hidden
          className={[
            "absolute top-0.5 left-0.5 h-6 w-6 md:h-6 md:w-6 sm:h-5 sm:w-5 rounded-full bg-white dark:bg-slate-100",
            "shadow-[0_2px_4px_rgba(0,0,0,.15),_0_8px_16px_rgba(0,0,0,.12)]",
          ].join(" ")}
          initial={false}
          animate={{
            x: checked ? THUMB_OFFSET_PX : 0,
            boxShadow: checked
              ? "0 2px 6px rgba(0,0,0,.2)"
              : "0 2px 4px rgba(0,0,0,.15), 0 8px 16px rgba(0,0,0,.12)",
          }}
          transition={{
            type: "spring",
            stiffness: 400,
            damping: 30,
          }}
        />

        <span
          className={[
            "pointer-events-none absolute -inset-1 rounded-[28px] transition-shadow duration-200",
            getFocusRingClasses(),
          ].join(" ")}
        />
      </span>

      {label && (
        <span
          className={[
            "text-sm text-slate-900 dark:text-slate-100/90 transition-colors duration-200",
            labelPosition === "left" ? "order-0" : checked ? "order-0" : "order-1",
            labelClassName ?? "",
          ].join(" ")}
        >
          {label}
        </span>
      )}
    </label>
  );
}

export const Toggle = memo(ToggleInner);
