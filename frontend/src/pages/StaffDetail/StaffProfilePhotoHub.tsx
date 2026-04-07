import { useEffect, useId, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FaCamera, FaChevronRight, FaImage, FaUserCheck } from "react-icons/fa";
import { Link } from "../../RouterUtils";

type ProfileAvatarWithPhotoMenuProps = {
  avatarSrc: string;
  avatarAlt: string;
  disabled?: boolean;
  onPickFile: () => void;
  onOpenCamera: () => void;
  uploadBusy?: boolean;
  sizeClassName?: string;
};

export function ProfileAvatarWithPhotoMenu({
  avatarSrc,
  avatarAlt,
  disabled,
  onPickFile,
  onOpenCamera,
  uploadBusy = false,
  sizeClassName = "h-20 w-20 lg:h-24 lg:w-24",
}: ProfileAvatarWithPhotoMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const busy = Boolean(disabled || uploadBusy);
  const close = () => setOpen(false);

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        className="group relative rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-gray-900"
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls={menuId}
        disabled={busy}
        onClick={() => !busy && setOpen((v) => !v)}
      >
        <div
          className={`relative overflow-hidden rounded-full border border-primary-200/90 shadow-md transition duration-200 ease-out group-hover:border-primary-300 group-hover:shadow-lg dark:border-primary-800/90 dark:group-hover:border-primary-600 ${sizeClassName} group-hover:scale-[1.02] active:scale-[0.99]`}
        >
          <img
            src={avatarSrc}
            alt={avatarAlt}
            className="h-full w-full object-cover"
          />
          <div
            className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center rounded-full bg-black/0 transition-colors duration-200 group-hover:bg-black/35 group-focus-visible:bg-black/35"
            aria-hidden
          >
            <FaCamera className="h-4 w-4 text-white opacity-0 drop-shadow transition-opacity duration-200 group-hover:opacity-100 group-focus-visible:opacity-100 sm:h-5 sm:w-5" />
          </div>
        </div>
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            id={menuId}
            role="menu"
            aria-label="Изменить фото профиля"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -2 }}
            transition={{ duration: 0.15 }}
            className="absolute z-[60] mt-1.5 w-[min(calc(100vw-2rem),15rem)] rounded-xl border border-gray-200/90 bg-white py-1 shadow-lg ring-1 ring-black/5 dark:border-gray-600 dark:bg-gray-800 dark:ring-white/10 left-1/2 -translate-x-1/2 sm:left-0 sm:translate-x-0"
          >
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm font-medium text-gray-900 transition hover:bg-gray-50 dark:text-gray-100 dark:hover:bg-gray-700/60"
              onClick={() => {
                onOpenCamera();
                close();
              }}
            >
              <FaCamera className="h-4 w-4 shrink-0 text-primary-600 dark:text-primary-400" />
              <span>Сделать фото</span>
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm font-medium text-gray-900 transition hover:bg-gray-50 dark:text-gray-100 dark:hover:bg-gray-700/60"
              onClick={() => {
                onPickFile();
                close();
              }}
            >
              <FaImage className="h-4 w-4 shrink-0 text-gray-500 dark:text-gray-400" />
              <span>Загрузить файл</span>
            </button>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

type ProfileFaceSetupCardProps = {
  href: string;
  anglesDone?: number;
  loading?: boolean;
  className?: string;
};

export function ProfileFaceSetupCard({
  href,
  anglesDone = 0,
  loading = false,
  className = "",
}: ProfileFaceSetupCardProps) {
  const done = Math.min(3, Math.max(0, anglesDone));
  const statusLine = loading
    ? "Проверяем…"
    : done >= 3
      ? "Все три ракурса есть — можно обновить"
      : done === 0
        ? "Сделайте три фото в Face Lab"
        : `Готово ${done} из 3`;

  return (
    <Link
      to={href}
      className={`group flex max-w-md items-center gap-2.5 rounded-lg border border-slate-200/90 bg-slate-50/80 px-3 py-2 transition hover:border-primary-200 hover:bg-primary-50/40 dark:border-slate-600/80 dark:bg-slate-800/40 dark:hover:border-primary-800 dark:hover:bg-primary-950/30 ${className}`}
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary-600 text-white dark:bg-primary-500">
        {done >= 3 ? (
          <FaUserCheck className="h-3.5 w-3.5" aria-hidden />
        ) : (
          <span className="text-[10px] font-bold tabular-nums">{done}/3</span>
        )}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
          Вход по лицу
        </p>
        <p className="text-xs leading-snug text-gray-500 dark:text-gray-400">
          {statusLine}
        </p>
      </div>
      <FaChevronRight
        className="h-3.5 w-3.5 shrink-0 text-gray-400 transition group-hover:translate-x-0.5 dark:text-gray-500"
        aria-hidden
      />
    </Link>
  );
}
