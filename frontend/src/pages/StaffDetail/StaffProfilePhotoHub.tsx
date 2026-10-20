import { useEffect, useId, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FaCamera, FaImage } from "react-icons/fa";

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
        aria-label="Изменить фото профиля"
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
            role="group"
            aria-label="Изменить фото профиля"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -2 }}
            transition={{ duration: 0.15 }}
            className="absolute left-0 z-[60] mt-1.5 w-[min(calc(100vw-5rem),15rem)] rounded-xl border border-gray-200/90 bg-white py-1 shadow-lg dark:border-gray-600 dark:bg-gray-800"
          >
            <button
              type="button"
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
