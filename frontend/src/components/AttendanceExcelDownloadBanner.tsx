import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FaHourglassHalf, FaFileExcel, FaTimes } from "react-icons/fa";
import { subscribeAttendanceExcelDownloads } from "../utils/attendanceExcelDownloadHub";
import {
  attendanceExcelInProgressDetail,
  attendanceExcelInProgressTitle,
} from "../utils/attendanceExcelCopy";

const shellCard =
  "rounded-2xl border shadow-lg ring-1 ring-inset " +
  "border-amber-200/90 bg-gradient-to-br from-amber-50/98 via-orange-50/95 to-amber-100/98 " +
  "ring-amber-900/[0.06] shadow-amber-900/10 backdrop-blur-md " +
  "dark:border-amber-500/45 dark:bg-gradient-to-br dark:from-gray-950 dark:via-zinc-900 dark:to-gray-950 " +
  "dark:shadow-[0_12px_40px_-10px_rgba(0,0,0,0.65)] dark:ring-amber-200/18 " +
  "dark:backdrop-blur-xl dark:backdrop-saturate-150";

const AttendanceExcelDownloadBanner: React.FC = () => {
  const [active, setActive] = useState(0);
  const [minimized, setMinimized] = useState(false);

  useEffect(() => subscribeAttendanceExcelDownloads(({ active: n }) => setActive(n)), []);

  useEffect(() => {
    if (active > 0) setMinimized(false);
  }, [active]);

  const title = attendanceExcelInProgressTitle(active);
  const detail = attendanceExcelInProgressDetail(active);

  return (
    <AnimatePresence>
      {active > 0 && (
        <motion.div
          className={[
            "fixed z-[880] max-w-[min(100vw-1.5rem,22rem)] sm:max-w-sm",
            "right-3 sm:right-4",
            "bottom-[calc(5.5rem+env(safe-area-inset-bottom,0px))] lg:bottom-6",
          ].join(" ")}
          initial={{ opacity: 0, x: 24, y: 12 }}
          animate={{ opacity: 1, x: 0, y: 0 }}
          exit={{ opacity: 0, x: 16, y: 8 }}
          transition={{ type: "spring", stiffness: 420, damping: 32 }}
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          {minimized ? (
            <button
              type="button"
              onClick={() => setMinimized(false)}
              className={`flex w-full items-center gap-2 px-3 py-2.5 text-left ${shellCard}`}
            >
              <motion.span
                animate={{ rotate: 360 }}
                transition={{ duration: 2.2, repeat: Infinity, ease: "linear" }}
                className="text-amber-700 dark:text-amber-300"
                aria-hidden
              >
                <FaHourglassHalf className="h-4 w-4" />
              </motion.span>
              <FaFileExcel className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" aria-hidden />
              <span className="min-w-0 flex-1 truncate text-sm font-semibold text-amber-950 dark:text-white">
                {title}
              </span>
              <span className="shrink-0 text-xs font-medium text-amber-800 dark:text-white/75">
                Развернуть
              </span>
            </button>
          ) : (
            <div className={`relative overflow-hidden ${shellCard}`}>
              <div
                className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-amber-500 via-orange-500 to-amber-400 dark:from-amber-400 dark:via-orange-400 dark:to-amber-500"
                aria-hidden
              />
              <div className="flex items-start gap-2.5 p-3 sm:gap-3 sm:p-3.5">
                <div
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border shadow-sm
                    border-amber-200/90 bg-white/95 dark:border-amber-600/40 dark:bg-gray-900/80"
                >
                  <FaFileExcel className="h-4 w-4 text-emerald-600 dark:text-emerald-400" aria-hidden />
                </div>
                <div className="min-w-0 flex-1 pt-0.5 pr-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <motion.span
                      animate={{ rotate: 360 }}
                      transition={{
                        duration: 2.2,
                        repeat: Infinity,
                        ease: "linear",
                      }}
                      className="inline-flex text-amber-700 dark:text-amber-300"
                      aria-hidden
                    >
                      <FaHourglassHalf className="h-3.5 w-3.5" />
                    </motion.span>
                    <p className="text-sm font-semibold leading-snug text-amber-950 dark:text-white">
                      {title}
                    </p>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-amber-900/95 dark:text-white/88">
                    {detail}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setMinimized(true)}
                  className="-mr-1 -mt-0.5 shrink-0 rounded-lg p-1.5 text-amber-800/75 transition-colors hover:bg-amber-200/60 hover:text-amber-950 dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white"
                  aria-label="Свернуть уведомление о загрузке"
                >
                  <FaTimes className="h-3.5 w-3.5" aria-hidden />
                </button>
              </div>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default AttendanceExcelDownloadBanner;
