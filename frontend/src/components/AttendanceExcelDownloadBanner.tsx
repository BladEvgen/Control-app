import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FaExclamationCircle, FaRedo, FaTimes } from "react-icons/fa";
import {
  subscribeAttendanceExcelDownloads,
  dismissAttendanceExcelError,
  type AttendanceExcelHubState,
} from "../utils/attendanceExcelDownloadHub";

const toastMotion = {
  initial: { opacity: 0, y: 16, scale: 0.97 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: 8, scale: 0.98 },
  transition: { duration: 0.25, ease: [0.22, 1, 0.36, 1] as const },
};

export default function AttendanceExcelDownloadBanner() {
  const [state, setState] = useState<AttendanceExcelHubState>({
    active: 0,
    holdCounts: new Map(),
    failedDownload: null,
  });
  useEffect(() => subscribeAttendanceExcelDownloads(setState), []);
  return (
    <div className="ws-toasts" aria-live="polite">
      <AnimatePresence>
        {state.active > 0 && (
          <motion.div
            key="active"
            className="ws-toast"
            role="status"
            {...toastMotion}
          >
            <span className="ws-spinner ws-toast-icon" aria-hidden />
            <div>
              Готовим Excel{state.active > 1 ? ` · ${state.active}` : ""}
            </div>
          </motion.div>
        )}
        {state.failedDownload && (
          <motion.div
            key="error"
            className="ws-toast is-error"
            role="alert"
            {...toastMotion}
          >
            <FaExclamationCircle className="ws-toast-icon" aria-hidden />
            <div>
              Не удалось скачать
              <small>{state.failedDownload.filename}</small>
            </div>
            <button
              type="button"
              className="ws-icon-button"
              onClick={() => void state.failedDownload?.retry()}
              aria-label="Повторить"
            >
              <FaRedo aria-hidden />
            </button>
            <button
              type="button"
              className="ws-icon-button"
              onClick={dismissAttendanceExcelError}
              aria-label="Закрыть"
            >
              <FaTimes aria-hidden />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
