import { motion } from "framer-motion";
import {
  FaSyncAlt,
  FaCheckCircle,
  FaThLarge,
  FaTimesCircle,
  FaCamera,
  FaSpinner,
} from "react-icons/fa";
import { CircleBtn } from "./CameraUIComponents";
import type { Aspect } from "./types";
import { vibrate } from "./camera-utils";

const ASPECT_OPTIONS: { value: Aspect; label: string; title?: string }[] = [
  { value: "3:4", label: "3:4", title: "Классическая вертикаль" },
  { value: "1:1", label: "1:1", title: "Квадрат — удобно для лица по центру" },
  {
    value: "4:3",
    label: "4:3",
    title: "Шире по горизонтали",
  },
];

type TopControlsProps = {
  onClose: () => void;
  gridOn: boolean;
  onToggleGrid: () => void;
  aspect: Aspect;
  onAspectChange: (aspect: Aspect) => void;
};

export function TopControls({
  onClose,
  gridOn,
  onToggleGrid,
  aspect,
  onAspectChange,
}: TopControlsProps) {
  const handleClose = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onClose();
  };

  const handleToggleGrid = (e: React.MouseEvent) => {
    e.preventDefault();
    onToggleGrid();
    vibrate([8]);
  };

  const handleAspectChange = (a: Aspect) => (e: React.MouseEvent) => {
    e.preventDefault();
    onAspectChange(a);
    vibrate([8]);
  };

  return (
    <motion.div
      className="absolute left-0 right-0 top-[max(12px,env(safe-area-inset-top))] z-30 flex items-center gap-2 px-3 sm:px-4"
      initial={{ y: -100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ delay: 0.2, type: "spring", stiffness: 200 }}
    >
      <motion.button
        type="button"
        onClick={handleClose}
        className="shrink-0 touch-none rounded-full bg-black/40 p-3.5 text-white shadow-[0_0_0_1px_rgba(255,255,255,0.1)_inset,0_2px_8px_rgba(0,0,0,0.3)] backdrop-blur-2xl active:bg-black/50 focus:outline-none focus-visible:ring-4 focus-visible:ring-white/70"
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.96 }}
        title="Закрыть"
        aria-label="Закрыть камеру"
        style={{ WebkitTapHighlightColor: "transparent" }}
      >
        <FaTimesCircle size={26} />
      </motion.button>

      <div className="min-w-0 flex-1 flex justify-end">
        <div className="flex max-w-full items-center gap-1.5 overflow-x-auto rounded-[18px] bg-black/40 px-2.5 py-2 shadow-[0_0_0_1px_rgba(255,255,255,0.1)_inset,0_4px_16px_rgba(0,0,0,0.35)] backdrop-blur-2xl [scrollbar-width:none] sm:gap-2 sm:px-3 sm:py-2.5 [&::-webkit-scrollbar]:hidden">
          <motion.button
            type="button"
            onClick={handleToggleGrid}
            aria-label={gridOn ? "Скрыть сетку" : "Показать сетку"}
            aria-pressed={gridOn}
            className={`shrink-0 touch-none rounded-[12px] p-2 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-white ${
              gridOn
                ? "bg-white/25 text-white shadow-[0_0_0_1px_rgba(255,255,255,0.2)_inset]"
                : "text-white/70 active:bg-white/10"
            }`}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.96 }}
            title="Сетка"
            style={{ WebkitTapHighlightColor: "transparent" }}
          >
            <motion.div
              animate={{ rotate: gridOn ? 0 : 180 }}
              transition={{ duration: 0.3 }}
            >
              <FaThLarge size={20} />
            </motion.div>
          </motion.button>

          <div className="h-6 w-px shrink-0 bg-white/15" />

          {ASPECT_OPTIONS.map(({ value: a, label, title }) => (
            <motion.button
              key={a}
              type="button"
              title={title}
              aria-label={`Формат кадра ${label}`}
              aria-pressed={aspect === a}
              className={`shrink-0 touch-none rounded-[12px] px-3 py-2 text-[11px] font-semibold transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-white sm:px-3.5 sm:text-xs ${
                aspect === a
                  ? "bg-white text-black shadow-[0_0_0_1px_rgba(255,255,255,0.15)_inset,0_1px_3px_rgba(0,0,0,0.2)]"
                  : "text-white/75 active:bg-white/10"
              }`}
              onClick={handleAspectChange(a)}
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.96 }}
              layout
              transition={{
                type: "spring",
                stiffness: 300,
                damping: 25,
              }}
              style={{ WebkitTapHighlightColor: "transparent" }}
            >
              {label}
            </motion.button>
          ))}
        </div>
      </div>
    </motion.div>
  );
}

type BottomControlsProps = {
  lastShotUrl: string | null;
  onDone: () => void;
  isCapturing: boolean;
  isCameraReady: boolean;
  onCapture: () => void;
  onToggleFacing: () => void;
  shouldMirror: boolean;
  captureDisabled?: boolean;
  captureHint?: string | null;
};

export function BottomControls({
  lastShotUrl,
  onDone,
  isCapturing,
  isCameraReady,
  onCapture,
  onToggleFacing,
  shouldMirror,
  captureDisabled,
  captureHint,
}: BottomControlsProps) {
  const isCaptureDisabled =
    !isCameraReady || isCapturing || Boolean(captureDisabled);

  return (
    <motion.div
      className="pointer-events-auto absolute inset-x-0 bottom-0 z-30 bg-gradient-to-t from-black/75 via-black/45 to-transparent pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-14 sm:pt-16"
      initial={{ y: 100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ delay: 0.3, type: "spring", stiffness: 200 }}
    >
      {captureHint ? (
        <p
          className="mx-auto mb-3 max-w-lg px-4 text-center text-sm font-semibold leading-snug text-white sm:max-w-xl sm:text-base [text-shadow:0_1px_4px_rgba(0,0,0,0.92)]"
          role="status"
          aria-live="polite"
        >
          {captureHint}
        </p>
      ) : null}
      <div className="mx-auto grid w-full max-w-[620px] grid-cols-3 items-end gap-4 px-4 sm:gap-5">
        <div className="flex justify-start">
          {lastShotUrl && (
            <CircleBtn
              title="Готово"
              icon={<FaCheckCircle size={28} />}
              onClick={onDone}
              size={64}
              kind="success"
            />
          )}
        </div>

        <div className="flex justify-center">
          <div className="relative">
            <CircleBtn
              title={
                !isCameraReady
                  ? "Ожидание камеры…"
                  : isCapturing
                    ? "Съёмка…"
                    : captureDisabled
                      ? captureHint || "Подготовка…"
                      : "Снимок"
              }
              icon={
                isCapturing ? (
                  <FaSpinner size={36} className="animate-spin" />
                ) : !isCameraReady ? (
                  <FaSpinner size={36} className="animate-spin opacity-50" />
                ) : (
                  <FaCamera size={36} />
                )
              }
              onClick={onCapture}
              size={88}
              kind="primary"
              disabled={isCaptureDisabled}
            />
            {isCameraReady && !isCapturing && !captureDisabled && (
              <>
                <motion.div
                  className="pointer-events-none absolute inset-0 rounded-full border-[2px] border-white/20"
                  animate={{
                    scale: [1, 1.15, 1],
                    opacity: [0.4, 0, 0.4],
                  }}
                  transition={{
                    duration: 2,
                    repeat: Infinity,
                    ease: "easeInOut",
                  }}
                />
                <motion.div
                  className="pointer-events-none absolute inset-0 rounded-full bg-white/5"
                  animate={{
                    scale: [1, 1.1, 1],
                  }}
                  transition={{
                    duration: 1.5,
                    repeat: Infinity,
                    ease: "easeInOut",
                  }}
                />
              </>
            )}
          </div>
        </div>

        <div className="flex justify-end">
          <CircleBtn
            title="Сменить камеру"
            icon={<FaSyncAlt size={28} />}
            onClick={onToggleFacing}
            size={64}
            disabled={!isCameraReady}
          />
        </div>
      </div>

      <motion.div
        className="mt-5 flex items-center justify-center gap-2.5 text-[13px] font-medium text-white/70"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5, duration: 0.3 }}
      >
        <motion.div
          animate={{
            scale: isCameraReady ? [1, 1.25, 1] : 1,
            opacity: isCameraReady ? [0.6, 1, 0.6] : 0.3,
          }}
          transition={{
            duration: 2,
            repeat: isCameraReady ? Infinity : 0,
            ease: "easeInOut",
          }}
          className={`h-[7px] w-[7px] rounded-full ${
            isCameraReady
              ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]"
              : "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.6)]"
          }`}
        />
        <motion.span
          key={`${shouldMirror}-${isCameraReady}`}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -5 }}
          transition={{ duration: 0.2 }}
        >
          {!isCameraReady ? "Камера…" : shouldMirror ? "Фронт" : "Основная"}
        </motion.span>
      </motion.div>
    </motion.div>
  );
}
