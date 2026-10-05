import { useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";

type DropdownProps = {
  trigger: (props: {
    open: boolean;
    toggle: () => void;
    "aria-expanded": boolean;
    "aria-haspopup": true;
  }) => ReactNode;
  children: ReactNode | ((close: () => void) => ReactNode);
  align?: "start" | "end";
  side?: "bottom" | "top";
  panelClassName?: string;
  closeKey?: string;
};

export default function Dropdown({
  trigger,
  children,
  align = "start",
  side = "bottom",
  panelClassName = "",
  closeKey,
}: DropdownProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const close = (): void => setOpen(false);

  useEffect(close, [closeKey]);
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent): void => {
      if (!rootRef.current?.contains(event.target as Node)) close();
    };
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="ws-dropdown">
      {trigger({
        open,
        toggle: () => setOpen((value) => !value),
        "aria-expanded": open,
        "aria-haspopup": true,
      })}
      <AnimatePresence>
        {open && (
          <motion.div
            className={`ws-dropdown-panel ${panelClassName}`}
            data-align={align}
            data-side={side}
            initial={{ opacity: 0, scale: 0.96, y: side === "top" ? 6 : -6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: side === "top" ? 4 : -4 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
          >
            {typeof children === "function" ? children(close) : children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
