import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
  useId,
} from "react";
import { createPortal } from "react-dom";
import { FaTimes, FaChevronLeft, FaChevronRight } from "react-icons/fa";
import { validRange } from "../utils/reportDates";

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

const POPOVER_W = 300;
const POPOVER_H_EST = 380;
const GRID_CELLS = 42;

function dateToStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function strToDate(s: string): Date | null {
  const [y, m, d] = s.split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

function shiftDays(base: Date, days: number): Date {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d;
}

function formatDdMmYyyy(s: string): string {
  const p = s.split("-");
  return p.length === 3 ? `${p[2]}.${p[1]}.${p[0]}` : s;
}

function formatFullRu(s: string): string {
  const d = strToDate(s);
  if (!d) return s;
  const label = d.toLocaleDateString("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  return label.charAt(0).toUpperCase() + label.slice(1);
}

interface CalCell {
  dateStr: string;
  label: string;
  day: number;
  isCurrent: boolean;
  isWeekend: boolean;
}

function buildGrid(year: number, month: number): CalCell[] {
  const first = new Date(year, month, 1);
  const start = shiftDays(first, -((first.getDay() + 6) % 7));
  return Array.from({ length: GRID_CELLS }, (_, i) => {
    const d = shiftDays(start, i);
    const dateStr = dateToStr(d);
    return {
      dateStr,
      label: formatFullRu(dateStr),
      day: d.getDate(),
      isCurrent: d.getMonth() === month,
      isWeekend: i % 7 >= 5,
    };
  });
}

interface EditableDateFieldProps {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  containerClassName?: string;
  displayClassName?: string;
  startIcon?: React.ReactNode;
  displayLabel?: string;
  isLoading?: boolean;
  ariaLabel?: string;
}

const EditableDateField: React.FC<EditableDateFieldProps> = ({
  value,
  onChange,
  containerClassName,
  displayClassName,
  startIcon,
  displayLabel,
  isLoading = false,
  ariaLabel,
}) => {
  const titleId = useId();
  const inputId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const [viewYear, setViewYear] = useState(() => new Date().getFullYear());
  const [viewMonth, setViewMonth] = useState(() => new Date().getMonth());
  const [popStyle, setPopStyle] = useState<React.CSSProperties>({});

  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const todayStr = useMemo(() => dateToStr(new Date()), []);
  const yesterdayStr = useMemo(() => dateToStr(shiftDays(new Date(), -1)), []);
  const maxDateStr = todayStr;

  const reposition = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const width = Math.min(POPOVER_W, vw - 16);
    const left = Math.max(
      8,
      Math.min(
        rect.left + width > vw - 8 ? rect.right - width : rect.left,
        vw - width - 8,
      ),
    );
    const top =
      vh - rect.bottom - 12 >= POPOVER_H_EST
        ? rect.bottom + 8
        : Math.max(8, rect.top - POPOVER_H_EST - 8);
    setPopStyle({ top, left, width, maxHeight: vh - top - 8 });
  }, []);

  const open = useCallback(() => {
    const d = strToDate(value) ?? new Date();
    setViewYear(d.getFullYear());
    setViewMonth(d.getMonth());
    reposition();
    setIsOpen(true);
  }, [value, reposition]);

  const close = useCallback(() => {
    setIsOpen(false);
    triggerRef.current?.focus();
  }, []);

  const apply = useCallback(
    (ds: string) => {
      if (ds !== value) {
        onChange({
          target: { value: ds },
        } as React.ChangeEvent<HTMLInputElement>);
      }
      close();
    },
    [onChange, close, value],
  );

  useEffect(() => {
    if (!isOpen) return;
    const onPointer = (e: MouseEvent) => {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t) || popoverRef.current?.contains(t))
        return;
      close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    const onScroll = (e: Event) => {
      if (popoverRef.current?.contains(e.target as Node)) return;
      close();
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, {
      capture: true,
      passive: true,
    });
    window.addEventListener("resize", reposition);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, { capture: true });
      window.removeEventListener("resize", reposition);
    };
  }, [isOpen, close, reposition]);

  const shiftMonth = useCallback(
    (delta: number) => {
      const d = new Date(viewYear, viewMonth + delta, 1);
      setViewYear(d.getFullYear());
      setViewMonth(d.getMonth());
    },
    [viewYear, viewMonth],
  );

  const isNextDisabled =
    dateToStr(new Date(viewYear, viewMonth + 1, 1)) > maxDateStr;

  const cells = useMemo(
    () => buildGrid(viewYear, viewMonth),
    [viewYear, viewMonth],
  );

  const relativeHint = useMemo(() => {
    if (!value) return null;
    if (value === todayStr) return "сегодня";
    if (value === yesterdayStr) return "вчера";
    const today = strToDate(todayStr);
    const picked = strToDate(value);
    if (!today || !picked) return null;
    const diff = Math.round((today.getTime() - picked.getTime()) / 86_400_000);
    return diff > 0 ? `${diff} дн. назад` : null;
  }, [value, todayStr, yesterdayStr]);

  const rawTriggerText = displayLabel ?? formatDdMmYyyy(value);
  const triggerText =
    rawTriggerText.charAt(0).toUpperCase() + rawTriggerText.slice(1);

  const popover = isOpen
    ? createPortal(
        <div
          ref={popoverRef}
          className="date-popover"
          role="dialog"
          aria-labelledby={titleId}
          style={popStyle}
        >
          <div className="date-popover-head">
            <span id={titleId}>Выберите дату</span>
            <button
              type="button"
              onClick={close}
              className="ws-input-action"
              aria-label="Закрыть"
            >
              <FaTimes aria-hidden />
            </button>
          </div>

          <div className="ws-input">
            <label htmlFor={inputId} className="sr-only">
              Дата
            </label>
            <input
              id={inputId}
              type="date"
              defaultValue={value}
              max={maxDateStr}
              onChange={(event) => {
                const date = event.target.value;
                if (
                  validRange({ startDate: date, endDate: date }) &&
                  date <= maxDateStr
                )
                  apply(date);
              }}
            />
          </div>

          <div className="date-popover-quick">
            {[
              { label: "Сегодня", val: todayStr },
              { label: "Вчера", val: yesterdayStr },
            ].map(({ label: lbl, val }) => (
              <button
                key={lbl}
                type="button"
                className="ws-chip"
                aria-pressed={value === val}
                onClick={() => apply(val)}
              >
                {lbl}
              </button>
            ))}
          </div>

          <div className="date-popover-month">
            <button
              type="button"
              className="ws-input-action"
              onClick={() => shiftMonth(-1)}
              aria-label="Предыдущий месяц"
            >
              <FaChevronLeft aria-hidden />
            </button>
            <span aria-live="polite">
              {MONTHS_RU[viewMonth]} {viewYear}
            </span>
            <button
              type="button"
              className="ws-input-action"
              onClick={() => shiftMonth(1)}
              disabled={isNextDisabled}
              aria-label="Следующий месяц"
            >
              <FaChevronRight aria-hidden />
            </button>
          </div>

          <div className="date-popover-grid" role="grid">
            {WEEKDAYS_SHORT.map((wd) => (
              <span key={wd} className="date-popover-weekday" aria-hidden>
                {wd}
              </span>
            ))}
            {cells.map((cell) => {
              const disabled = cell.dateStr > maxDateStr;
              return (
                <button
                  key={cell.dateStr}
                  type="button"
                  className="date-popover-day"
                  disabled={disabled}
                  data-outside={!cell.isCurrent || undefined}
                  data-weekend={cell.isWeekend || undefined}
                  data-today={cell.dateStr === todayStr || undefined}
                  aria-pressed={cell.dateStr === value}
                  aria-label={cell.label}
                  onClick={() => apply(cell.dateStr)}
                >
                  {cell.day}
                </button>
              );
            })}
          </div>

          {value && (
            <p className="date-popover-foot">
              {formatFullRu(value)}
              {relativeHint && ` · ${relativeHint}`}
            </p>
          )}
        </div>,
        document.body,
      )
    : null;

  return (
    <div className={containerClassName}>
      <button
        ref={triggerRef}
        type="button"
        onClick={open}
        aria-label={ariaLabel ?? "Выбрать дату"}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        className={`date-field-trigger ${displayClassName ?? "ws-chip"}`}
      >
        {startIcon}
        <span>{triggerText}</span>
        {isLoading && <span aria-hidden className="ws-spinner" />}
      </button>

      {popover}
    </div>
  );
};

export default EditableDateField;
