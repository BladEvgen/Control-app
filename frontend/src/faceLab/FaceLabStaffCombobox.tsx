import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FaUserCheck } from "react-icons/fa";

export type StaffPickOption = {
  pin: string;
  fio: string;
  deptName: string;
  deptId: number;
  faceProfileState?: string;
};

function normalizeSearch(s: string): string {
  return s.trim().toLowerCase().normalize("NFKD").replace(/\p{M}/gu, "");
}

function formatLabel(o: StaffPickOption): string {
  const base = `${o.fio} — ${o.deptName}`;
  if (o.faceProfileState === "bootstrap_required") {
    return `${base} · нужен сбор лиц`;
  }
  if (o.faceProfileState === "weak_gallery") {
    return `${base} · слабая галерея`;
  }
  return base;
}

type Props = {
  options: StaffPickOption[];
  value: string;
  onChange: (pin: string) => void;
  disabled?: boolean;
  loading?: boolean;
  placeholder?: string;
  focusRequestId?: number;
};

const LIST_PREVIEW = 80;
const LIST_SEARCH = 100;

function tokensMatch(haystackNorm: string, queryNorm: string): boolean {
  if (!queryNorm) return true;
  const parts = queryNorm.split(/\s+/).filter(Boolean);
  return parts.every((p) => haystackNorm.includes(p));
}

export function FaceLabStaffCombobox({
  options,
  value,
  onChange,
  disabled,
  loading,
  placeholder = "ФИО или отдел",
  focusRequestId = 0,
}: Props) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [highlight, setHighlight] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const selected = useMemo(
    () => options.find((o) => o.pin === value) ?? null,
    [options, value],
  );

  const optionsIndexed = useMemo(
    () =>
      options.map((o) => ({
        o,
        hay: normalizeSearch(`${o.fio} ${o.deptName}`),
      })),
    [options],
  );

  useEffect(() => {
    if (selected) {
      setText(formatLabel(selected));
    } else if (!value) {
      setText("");
    }
  }, [selected, value]);

  const filtered = useMemo(() => {
    const nq = normalizeSearch(text);
    if (!nq) {
      return optionsIndexed.slice(0, LIST_PREVIEW).map((x) => x.o);
    }
    const out: StaffPickOption[] = [];
    for (
      let i = 0;
      i < optionsIndexed.length && out.length < LIST_SEARCH;
      i += 1
    ) {
      const { o, hay } = optionsIndexed[i];
      if (tokensMatch(hay, nq)) out.push(o);
    }
    return out;
  }, [optionsIndexed, text]);

  useEffect(() => {
    if (!focusRequestId) return;
    inputRef.current?.focus();
    setOpen(true);
  }, [focusRequestId]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
        if (selected) {
          setText(formatLabel(selected));
        } else if (!value) {
          setText("");
        }
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [selected, value]);

  useEffect(() => {
    setHighlight(0);
  }, [text, open, filtered.length]);

  const pick = useCallback(
    (o: StaffPickOption) => {
      setText(formatLabel(o));
      setOpen(false);
      onChange(o.pin);
      inputRef.current?.blur();
    },
    [onChange],
  );

  const onInputChange = (v: string) => {
    setText(v);
    setOpen(true);
    onChange("");
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      setOpen(false);
      if (selected) {
        setText(formatLabel(selected));
      }
      e.preventDefault();
      return;
    }
    if (!open && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      setOpen(true);
      e.preventDefault();
      return;
    }
    if (!open) return;
    if (e.key === "ArrowDown") {
      setHighlight((i) => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
      e.preventDefault();
    } else if (e.key === "ArrowUp") {
      setHighlight((i) => Math.max(i - 1, 0));
      e.preventDefault();
    } else if (e.key === "Enter" && filtered.length > 0) {
      pick(filtered[highlight]);
      e.preventDefault();
    }
  };

  const total = options.length;
  const shown = filtered.length;
  const nq = normalizeSearch(text);
  const listHint =
    !loading && total > 0
      ? !nq
        ? total > LIST_PREVIEW
          ? `Первые ${shown} из ${total} — введите фильтр`
          : `${total} в списке`
        : shown === 0
          ? null
          : shown >= LIST_SEARCH
            ? `${shown}+ совпадений — уточните запрос`
            : `Совпадений: ${shown}`
      : null;

  return (
    <div ref={rootRef} className="relative">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <label className="text-sm text-slate-600 dark:text-slate-400">
          Сотрудник
        </label>
        {listHint ? (
          <span className="text-xs text-slate-500" aria-live="polite">
            {listHint}
          </span>
        ) : null}
      </div>
      <input
        ref={inputRef}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls="face-lab-staff-listbox"
        aria-autocomplete="list"
        disabled={disabled || loading}
        placeholder={loading ? "Загрузка…" : placeholder}
        value={text}
        onChange={(e) => onInputChange(e.target.value)}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        autoComplete="off"
        className={`min-h-[44px] w-full rounded-lg border bg-white px-3 py-2.5 text-base text-slate-900 outline-none placeholder:text-slate-400 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-500/30 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-slate-500 sm:text-sm ${
          selected && value
            ? "border-emerald-400/80 ring-2 ring-emerald-500/25 dark:border-emerald-600/60 dark:ring-emerald-400/20"
            : "border-slate-300 dark:border-slate-600"
        }`}
      />
      {selected && value ? (
        <div className="mt-2 flex items-start gap-3 rounded-xl border border-emerald-200/90 bg-gradient-to-br from-emerald-50/95 to-white px-3 py-2.5 shadow-sm dark:border-emerald-800/50 dark:from-emerald-950/40 dark:to-slate-900/80">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-white dark:bg-emerald-700">
            <FaUserCheck className="h-4 w-4" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-emerald-800 dark:text-emerald-300/90">
              Выбрано
            </p>
            <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
              {selected.fio}
            </p>
            <p className="truncate text-xs text-slate-600 dark:text-slate-400">
              {selected.deptName}
            </p>
          </div>
        </div>
      ) : null}
      {open && !loading && filtered.length > 0 ? (
        <ul
          id="face-lab-staff-listbox"
          role="listbox"
          className="absolute z-50 mt-1 max-h-[min(24rem,min(70vh,65dvh))] w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-xl ring-1 ring-slate-900/10 dark:border-slate-600 dark:bg-slate-900 dark:ring-black/40"
        >
          {filtered.map((o, idx) => (
            <li
              key={`${o.pin}-${o.deptId}`}
              role="option"
              aria-selected={idx === highlight}
              className={`cursor-pointer px-3 py-2.5 text-sm transition-colors ${
                idx === highlight
                  ? "bg-indigo-50 dark:bg-slate-700/90"
                  : "hover:bg-slate-100 dark:hover:bg-slate-800"
              }`}
              onMouseDown={(ev) => ev.preventDefault()}
              onClick={() => pick(o)}
              onMouseEnter={() => setHighlight(idx)}
            >
              <span className="font-medium text-slate-900 dark:text-slate-100">
                {o.fio}
              </span>
              <span className="mt-0.5 block text-xs leading-snug text-slate-600 dark:text-slate-400">
                {o.deptName}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {open && !loading && filtered.length === 0 && normalizeSearch(text) ? (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-500 shadow-md dark:border-slate-600 dark:bg-slate-900">
          Ничего не найдено
        </div>
      ) : null}
    </div>
  );
}
