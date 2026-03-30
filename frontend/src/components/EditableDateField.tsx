import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  FaRegCalendarAlt,
  FaTimes,
  FaChevronLeft,
  FaChevronRight,
} from "react-icons/fa";

const MONTHS_RU = [
  "Январь",
  "Февраль",
  "Март",
  "Апрель",
  "Май",
  "Июнь",
  "Июль",
  "Август",
  "Сентябрь",
  "Октябрь",
  "Ноябрь",
  "Декабрь",
];

const WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

function dateToStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function strToDate(s: string): Date | null {
  const parts = s.split("-").map(Number);
  if (parts.length !== 3) return null;
  const [y, m, d] = parts;
  if (isNaN(y) || isNaN(m) || isNaN(d)) return null;
  return new Date(y, m - 1, d);
}

function getTodayStr() {
  return dateToStr(new Date());
}

function getYesterdayStr() {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return dateToStr(d);
}

function formatDdMmYyyy(s: string): string {
  const p = s.split("-");
  if (p.length !== 3) return s;
  return `${p[2]}.${p[1]}.${p[0]}`;
}

function formatFullRu(s: string): string {
  const d = strToDate(s);
  if (!d) return s;
  try {
    return d.toLocaleDateString("ru-RU", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  } catch {
    return formatDdMmYyyy(s);
  }
}


interface CalCell {
  dateStr: string;
  day: number;
  isCurrent: boolean;
  isToday: boolean;
  isSelected: boolean;
  isDisabled: boolean;
  isWeekend: boolean;
}

function buildGrid(
  year: number,
  month: number,
  selectedStr: string,
  todayStr: string,
  maxDate: string,
): CalCell[] {
  const firstDay = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const daysInPrev = new Date(year, month, 0).getDate();

  const firstDow = (firstDay.getDay() + 6) % 7;

  const cells: CalCell[] = [];

  for (let i = firstDow - 1; i >= 0; i--) {
    const d = new Date(year, month - 1, daysInPrev - i);
    const ds = dateToStr(d);
    const dow = (d.getDay() + 6) % 7;
    cells.push({
      dateStr: ds,
      day: daysInPrev - i,
      isCurrent: false,
      isToday: ds === todayStr,
      isSelected: ds === selectedStr,
      isDisabled: ds > maxDate,
      isWeekend: dow >= 5,
    });
  }

  for (let n = 1; n <= daysInMonth; n++) {
    const d = new Date(year, month, n);
    const ds = dateToStr(d);
    const dow = (d.getDay() + 6) % 7;
    cells.push({
      dateStr: ds,
      day: n,
      isCurrent: true,
      isToday: ds === todayStr,
      isSelected: ds === selectedStr,
      isDisabled: ds > maxDate,
      isWeekend: dow >= 5,
    });
  }

  const remaining = 42 - cells.length;
  for (let n = 1; n <= remaining; n++) {
    const d = new Date(year, month + 1, n);
    const ds = dateToStr(d);
    const dow = (d.getDay() + 6) % 7;
    cells.push({
      dateStr: ds,
      day: n,
      isCurrent: false,
      isToday: ds === todayStr,
      isSelected: ds === selectedStr,
      isDisabled: ds > maxDate,
      isWeekend: dow >= 5,
    });
  }

  return cells;
}


interface EditableDateFieldProps {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  label?: string;
  containerClassName?: string;
  labelClassName?: string;
  displayClassName?: string;
  inputClassName?: string;
  startIcon?: React.ReactNode;
  displayLabel?: string;
  isLoading?: boolean;
  maxDate?: string;
  ariaLabel?: string;
}


const POPOVER_W = 308;
const POPOVER_H_EST = 400;


const EditableDateField: React.FC<EditableDateFieldProps> = ({
  value,
  onChange,
  label,
  containerClassName,
  labelClassName,
  displayClassName,
  startIcon,
  displayLabel,
  isLoading = false,
  maxDate,
  ariaLabel,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [draft, setDraft] = useState(value);
  const [viewYear, setViewYear] = useState(() => new Date().getFullYear());
  const [viewMonth, setViewMonth] = useState(() => new Date().getMonth());
  const [popStyle, setPopStyle] = useState<React.CSSProperties>({});

  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const todayStr = useMemo(getTodayStr, []);
  const yesterdayStr = useMemo(getYesterdayStr, []);
  const maxDateStr = maxDate ?? todayStr;

  useEffect(() => {
    if (!isOpen) setDraft(value);
  }, [value, isOpen]);

  const reposition = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let left = rect.left;
    if (left + POPOVER_W > vw - 12) left = rect.right - POPOVER_W;
    left = Math.max(8, Math.min(left, vw - POPOVER_W - 8));

    const below = vh - rect.bottom - 12;
    const top =
      below >= POPOVER_H_EST
        ? rect.bottom + 8
        : Math.max(8, rect.top - POPOVER_H_EST - 8);

    setPopStyle({ top, left, width: POPOVER_W });
  }, []);

  const open = useCallback(() => {
    const d = strToDate(value) ?? new Date();
    setDraft(value);
    setViewYear(d.getFullYear());
    setViewMonth(d.getMonth());
    reposition();
    setIsOpen(true);
  }, [value, reposition]);

  const apply = useCallback(
    (ds: string) => {
      onChange({ target: { value: ds } } as React.ChangeEvent<HTMLInputElement>);
      setIsOpen(false);
    },
    [onChange],
  );

  const cancel = useCallback(() => {
    setDraft(value);
    setIsOpen(false);
  }, [value]);

  useEffect(() => {
    if (!isOpen) return;
    const onMouse = (e: MouseEvent) => {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t) || popoverRef.current?.contains(t))
        return;
      cancel();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") cancel();
    };
    const onScroll = () => cancel();
    const onResize = () => reposition();

    document.addEventListener("mousedown", onMouse);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, { capture: true, passive: true });
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("mousedown", onMouse);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, { capture: true });
      window.removeEventListener("resize", onResize);
    };
  }, [isOpen, cancel, reposition]);

  const prevMonth = useCallback(() => {
    setViewMonth((m) => {
      if (m === 0) {
        setViewYear((y) => y - 1);
        return 11;
      }
      return m - 1;
    });
  }, []);

  const nextMonth = useCallback(() => {
    const nextFirstStr = dateToStr(new Date(viewYear, viewMonth + 1, 1));
    if (nextFirstStr > maxDateStr) return;
    setViewMonth((m) => {
      if (m === 11) {
        setViewYear((y) => y + 1);
        return 0;
      }
      return m + 1;
    });
  }, [viewYear, viewMonth, maxDateStr]);

  const isNextDisabled = useMemo(() => {
    const nextFirst = dateToStr(new Date(viewYear, viewMonth + 1, 1));
    return nextFirst > maxDateStr;
  }, [viewYear, viewMonth, maxDateStr]);

  const cells = useMemo(
    () => buildGrid(viewYear, viewMonth, draft, todayStr, maxDateStr),
    [viewYear, viewMonth, draft, todayStr, maxDateStr],
  );

  const footerLabel = useMemo(() => {
    if (!draft) return null;
    const full = formatFullRu(draft);
    if (draft === todayStr) return `${full} — сегодня`;
    if (draft === yesterdayStr) return `${full} — вчера`;
    const diff = Math.round(
      (new Date(todayStr).getTime() - new Date(draft).getTime()) / 86400000,
    );
    if (diff > 0) return `${full} — ${diff} дн. назад`;
    return full;
  }, [draft, todayStr, yesterdayStr]);

  const cellCls = useCallback((c: CalCell): string => {
    const base =
      "relative flex items-center justify-center rounded-lg text-[12px] font-medium select-none transition-all duration-100 aspect-square focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1";

    if (c.isDisabled) {
      return `${base} text-slate-300 dark:text-slate-600 cursor-not-allowed`;
    }
    if (c.isSelected) {
      return `${base} bg-blue-600 text-white shadow-lg scale-[1.08] z-10 cursor-pointer`;
    }
    if (c.isToday) {
      return `${base} ring-1 ring-blue-400 dark:ring-blue-500 font-semibold text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/30 cursor-pointer hover:bg-blue-100 dark:hover:bg-blue-900/50`;
    }
    if (!c.isCurrent) {
      return `${base} text-slate-300 dark:text-slate-600 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/40 hover:text-slate-500 dark:hover:text-slate-400`;
    }
    if (c.isWeekend) {
      return `${base} text-rose-500 dark:text-rose-400 cursor-pointer hover:bg-rose-50 dark:hover:bg-rose-900/20`;
    }
    return `${base} text-slate-700 dark:text-slate-200 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-700/60`;
  }, []);

  const triggerText = displayLabel ?? formatDdMmYyyy(value);

  const defaultTriggerCls =
    "cursor-pointer transition-colors duration-150 hover:text-blue-600 dark:hover:text-blue-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded";

  const popover = createPortal(
    <AnimatePresence>
      {isOpen && (
        <div
          ref={popoverRef}
          className="fixed z-[9999]"
          style={popStyle}
        >
        <motion.div
          key="dp"
          initial={{ opacity: 0, scale: 0.93, y: -10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.93, y: -10 }}
          transition={{ type: "spring", damping: 28, stiffness: 440, mass: 0.6 }}
          className="rounded-2xl border border-slate-200 dark:border-slate-700/80 bg-white dark:bg-slate-900 shadow-[0_20px_60px_-8px_rgba(0,0,0,0.18),0_0_0_1px_rgba(0,0,0,0.04)] dark:shadow-[0_20px_60px_-8px_rgba(0,0,0,0.6)] overflow-hidden select-none"
        >
          <div className="flex items-center justify-between px-4 pt-3.5 pb-3 border-b border-slate-100 dark:border-slate-700/60">
            <div className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
              <FaRegCalendarAlt className="w-3.5 h-3.5 opacity-60 shrink-0" />
              <span className="text-[12.5px] font-semibold tracking-tight">
                Выберите дату
              </span>
            </div>
            <button
              type="button"
              onClick={cancel}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              aria-label="Закрыть"
            >
              <FaTimes className="w-3 h-3" />
            </button>
          </div>

          <div className="flex items-center gap-2 px-4 pt-3 pb-2.5">
            {[
              { label: "Сегодня", val: todayStr },
              { label: "Вчера", val: yesterdayStr },
            ].map(({ label: lbl, val }) => (
              <button
                key={lbl}
                type="button"
                onClick={() => apply(val)}
                className={`px-3 py-1 rounded-full text-[11px] font-medium border transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                  value === val
                    ? "bg-blue-600 text-white border-blue-600 shadow-sm"
                    : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-600 hover:border-blue-400 hover:text-blue-600 dark:hover:text-blue-300"
                }`}
              >
                {lbl}
              </button>
            ))}
          </div>

          <div className="flex items-center justify-between px-3 pb-2">
            <button
              type="button"
              onClick={prevMonth}
              className="p-1.5 rounded-lg text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              aria-label="Предыдущий месяц"
            >
              <FaChevronLeft className="w-3 h-3" />
            </button>

            <span className="text-[13px] font-semibold text-slate-700 dark:text-slate-200">
              {MONTHS_RU[viewMonth]}&nbsp;{viewYear}
            </span>

            <button
              type="button"
              onClick={nextMonth}
              disabled={isNextDisabled}
              className="p-1.5 rounded-lg text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors disabled:opacity-25 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              aria-label="Следующий месяц"
            >
              <FaChevronRight className="w-3 h-3" />
            </button>
          </div>

          <div className="grid grid-cols-7 px-3 mb-0.5">
            {WEEKDAYS_SHORT.map((wd, i) => (
              <div
                key={wd}
                className={`text-center text-[10px] font-medium py-1 ${
                  i >= 5
                    ? "text-rose-400/80 dark:text-rose-400/50"
                    : "text-slate-400 dark:text-slate-500"
                }`}
              >
                {wd}
              </div>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-px px-3 pb-3">
            {cells.map((cell) => (
              <button
                key={cell.dateStr}
                type="button"
                disabled={cell.isDisabled}
                tabIndex={cell.isDisabled ? -1 : 0}
                onClick={() => {
                  if (!cell.isDisabled) {
                    setDraft(cell.dateStr);
                    apply(cell.dateStr);
                  }
                }}
                className={cellCls(cell)}
              >
                {cell.day}
                {cell.isToday && !cell.isSelected && (
                  <span className="absolute bottom-[3px] left-1/2 -translate-x-1/2 w-[3px] h-[3px] rounded-full bg-blue-500" />
                )}
              </button>
            ))}
          </div>

          {footerLabel && (
            <div className="px-4 pt-2 pb-3.5 border-t border-slate-100 dark:border-slate-700/60">
              <p className="text-center text-[11px] text-slate-400 dark:text-slate-500 leading-snug capitalize">
                {footerLabel}
              </p>
            </div>
          )}
        </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );

  return (
    <div className={containerClassName ?? "flex flex-col items-center"}>
      {label && (
        <label className={labelClassName ?? "mb-2 text-center text-sm text-white"}>
          {label}
        </label>
      )}

      <button
        ref={triggerRef}
        type="button"
        onClick={open}
        aria-label={ariaLabel ?? "Выбрать дату"}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        className={displayClassName ?? defaultTriggerCls}
      >
        {startIcon}
        <span className={startIcon ? "capitalize" : undefined}>{triggerText}</span>
        {isLoading && (
          <span
            aria-hidden
            className="inline-block w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin shrink-0 opacity-70"
          />
        )}
      </button>

      {popover}
    </div>
  );
};

export default EditableDateField;
