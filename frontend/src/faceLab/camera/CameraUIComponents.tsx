import { useEffect } from "react";
import type { CSSProperties } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FaTimesCircle, FaExclamationTriangle } from "react-icons/fa";
import type { Aspect, CameraGuidanceContext, Frame } from "./types";
import { vibrate } from "./camera-utils";

type CircleBtnProps = {
  title?: string;
  onClick?: () => void;
  icon: React.ReactNode;
  size?: number;
  kind?: "neutral" | "primary" | "success";
  disabled?: boolean;
};

export function CircleBtn({
  title,
  onClick,
  icon,
  size = 64,
  kind = "neutral",
  disabled,
}: CircleBtnProps) {
  const theme =
    kind === "primary"
      ? "bg-white text-black hover:bg-white/90 active:bg-white/80 ring-white/40 shadow-xl"
      : kind === "success"
        ? "bg-emerald-500 text-white hover:bg-emerald-400 active:bg-emerald-500 ring-emerald-400/40 shadow-xl shadow-emerald-500/30"
        : "bg-white/15 text-white ring-white/30 backdrop-blur-xl hover:bg-white/25 active:bg-white/15 shadow-lg";

  const handleClick = (e: React.MouseEvent) => {
    if (disabled || !onClick) return;
    e.preventDefault();
    e.stopPropagation();
    vibrate([10]);
    onClick();
  };

  return (
    <motion.button
      type="button"
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={handleClick}
      whileHover={{ scale: disabled ? 1 : 1.08 }}
      whileTap={{ scale: disabled ? 1 : 0.92 }}
      className={`inline-flex items-center justify-center rounded-full ring-2 transition-all duration-200 focus:outline-none focus-visible:ring-4 touch-none ${theme} ${
        disabled ? "opacity-50 cursor-not-allowed" : ""
      }`}
      style={{
        width: size,
        height: size,
        WebkitTapHighlightColor: "transparent",
      }}
    >
      {icon}
    </motion.button>
  );
}

type VideoFrameProps = {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  shouldMirror: boolean;
  onTapToFocus: (e: React.PointerEvent) => void;
};

export function VideoFrame({
  videoRef,
  shouldMirror,
  onTapToFocus,
}: VideoFrameProps) {
  return (
    <video
      ref={videoRef as React.Ref<HTMLVideoElement>}
      autoPlay
      playsInline
      muted
      onPointerDown={onTapToFocus}
      className="absolute inset-0 h-full w-full object-cover object-center bg-black select-none touch-none"
      style={{
        WebkitTapHighlightColor: "transparent",
        transformOrigin: "center center",
        ...(shouldMirror
          ? {
              transform: "scaleX(-1) translateZ(0)",
              WebkitTransform: "scaleX(-1) translateZ(0)",
            }
          : {
              transform: "translateZ(0)",
              WebkitTransform: "translateZ(0)",
            }),
      }}
    />
  );
}

type AspectMaskProps = {
  frame: Frame;
  aspect: Aspect;
};

function FacePoseSilhouette({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 150" className={className} aria-hidden>
      <path
        d="M60 18c-18.8 0-32 14.7-32 35.7 0 23.8 13 43.5 32 43.5s32-19.7 32-43.5C92 32.7 78.8 18 60 18Z"
        fill="rgba(230,242,255,0.86)"
        stroke="rgba(255,255,255,0.96)"
        strokeWidth="3"
      />
      <path
        d="M19 137c4.2-24.7 21.5-38 41-38s36.8 13.3 41 38"
        fill="rgba(255,255,255,0.16)"
        stroke="rgba(255,255,255,0.78)"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <path
        d="M34 55h52"
        stroke="rgba(16,24,40,0.24)"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <path
        d="M60 23v107"
        stroke="rgba(16,24,40,0.2)"
        strokeDasharray="6 7"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ProfileYawSwing({ direction }: { direction: "left" | "right" }) {
  const shift = direction === "left" ? [0, -10, 0] : [0, 10, 0];
  return (
    <motion.span
      className="block h-1.5 w-8 rounded-full bg-white/85"
      animate={{ x: shift }}
      transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
      aria-hidden
    />
  );
}

function ViewfinderYawTurnFace3D({
  direction,
}: {
  direction: "left" | "right";
}) {
  const yDeg = direction === "left" ? -22 : 22;
  const directionLabel = "Поворачивайтесь медленно, без наклона головы";
  return (
    <div className="flex max-w-[min(92%,240px)] flex-col items-center gap-3">
      <div
        className="relative flex h-[min(31vw,7.25rem)] w-[min(31vw,7.25rem)] min-h-[108px] min-w-[108px] items-center justify-center rounded-[2rem] border border-white/20 bg-black/28 px-2 py-2 shadow-[0_18px_45px_rgba(0,0,0,0.35)] backdrop-blur-sm sm:h-32 sm:w-32"
        style={{
          perspective: "280px",
          perspectiveOrigin: "50% 42%",
        }}
      >
        <motion.div
          className="absolute inset-3 rounded-[1.45rem] border border-white/30"
          animate={{ opacity: [0.32, 0.75, 0.32], scale: [0.97, 1.04, 0.97] }}
          transition={{ duration: 1.9, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.div
          className={`absolute ${direction === "left" ? "left-[-0.75rem]" : "right-[-0.75rem]"} top-1/2 h-11 w-11 -translate-y-1/2`}
          animate={{
            x: direction === "left" ? [0, -8, 0] : [0, 8, 0],
            opacity: [0.72, 1, 0.72],
          }}
          transition={{ duration: 1.7, repeat: Infinity, ease: "easeInOut" }}
          aria-hidden
        >
          <svg viewBox="0 0 44 44" className="h-full w-full drop-shadow-lg">
            <path
              d={
                direction === "left"
                  ? "M27 10 15 22l12 12M17 22h20"
                  : "M17 10l12 12-12 12M7 22h20"
              }
              fill="none"
              stroke="rgba(255,255,255,0.96)"
              strokeWidth="4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </motion.div>
        <div
          className="pointer-events-none absolute inset-0 flex items-center justify-center"
          aria-hidden
        >
          <FacePoseSilhouette className="h-full w-full opacity-[0.16] saturate-0" />
        </div>
        <motion.div
          className="relative flex h-full w-full items-center justify-center will-change-transform"
          animate={{ rotateY: [0, yDeg, 0] }}
          transition={{
            duration: 2.35,
            repeat: Infinity,
            ease: "easeInOut",
          }}
          style={{
            transformStyle: "preserve-3d",
            backfaceVisibility: "hidden",
          }}
        >
          <FacePoseSilhouette className="h-full w-full drop-shadow-[0_8px_22px_rgba(0,0,0,0.5)]" />
        </motion.div>
      </div>

      <ProfileYawSwing direction={direction} />

      <div className="text-center leading-tight">
        <p
          className="text-[10px] font-semibold text-white [text-shadow:0_1px_4px_rgba(0,0,0,0.9)] sm:text-[11px]"
          style={{ fontFamily: "system-ui, sans-serif" }}
        >
          {directionLabel}
        </p>
      </div>
    </div>
  );
}

function ViewfinderFrontFaceGuide() {
  return (
    <div className="flex max-w-[min(92%,240px)] flex-col items-center gap-3">
      <div className="relative flex h-[min(31vw,7.25rem)] w-[min(31vw,7.25rem)] min-h-[108px] min-w-[108px] items-center justify-center rounded-[2rem] border border-white/22 bg-black/28 px-2 py-2 shadow-[0_18px_45px_rgba(0,0,0,0.35)] backdrop-blur-sm sm:h-32 sm:w-32">
        <motion.div
          className="absolute inset-2 rounded-[1.65rem] border border-white/45"
          animate={{ scale: [0.96, 1.04, 0.96], opacity: [0.45, 0.92, 0.45] }}
          transition={{ duration: 1.7, repeat: Infinity, ease: "easeInOut" }}
        />
        <div className="absolute left-1/2 top-2 h-[calc(100%-1rem)] w-px -translate-x-1/2 bg-white/20" />
        <div className="absolute left-2 top-1/2 h-px w-[calc(100%-1rem)] -translate-y-1/2 bg-white/16" />
        <motion.div
          className="relative flex h-full w-full items-center justify-center"
          animate={{ y: [0, -3, 0] }}
          transition={{ duration: 2.1, repeat: Infinity, ease: "easeInOut" }}
        >
          <FacePoseSilhouette className="h-full w-full drop-shadow-[0_8px_22px_rgba(0,0,0,0.5)]" />
        </motion.div>
      </div>
      <div className="rounded-full bg-black/35 px-3 py-1.5 text-[11px] font-semibold text-white/90 ring-1 ring-white/20 backdrop-blur-sm">
        Лицо по центру
      </div>
    </div>
  );
}

export function ViewfinderBootstrapHint({
  frame,
  context,
}: {
  frame: Frame;
  context: CameraGuidanceContext;
}) {
  if (frame.w < 20 || frame.h < 20) return null;

  const boxStyle: CSSProperties = {
    position: "absolute",
    width: `${frame.w}px`,
    height: `${frame.h}px`,
    left: `${frame.left}px`,
    top: `${frame.top}px`,
  };

  if (context === "bootstrap_front") {
    return (
      <div className="pointer-events-none absolute z-[26]" style={boxStyle}>
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 px-2">
          <ViewfinderFrontFaceGuide />
        </div>
      </div>
    );
  }

  if (context === "profile_photo") return null;

  if (context === "bootstrap_left" || context === "bootstrap_right") {
    const toLeft = context === "bootstrap_left";
    return (
      <div className="pointer-events-none absolute z-[26]" style={boxStyle}>
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 px-2">
          <ViewfinderYawTurnFace3D direction={toLeft ? "left" : "right"} />
        </div>
      </div>
    );
  }

  return null;
}

export function AspectMask({ frame, aspect }: AspectMaskProps) {
  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute inset-0 bg-black/28" />
      {frame.w > 10 && frame.h > 10 && (
        <motion.div
          key={aspect}
          className="absolute ring-2 ring-white/70 rounded-xl shadow-2xl"
          style={{
            width: `${frame.w}px`,
            height: `${frame.h}px`,
            left: `${frame.left}px`,
            top: `${frame.top}px`,
          }}
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
        >
          {[
            "top-0 left-0",
            "top-0 right-0",
            "bottom-0 left-0",
            "bottom-0 right-0",
          ].map((pos, i) => (
            <div
              key={i}
              className={`absolute ${pos} w-6 h-6 border-white/90`}
              style={{
                borderTopWidth: pos.includes("top") ? "3px" : 0,
                borderLeftWidth: pos.includes("left") ? "3px" : 0,
                borderRightWidth: pos.includes("right") ? "3px" : 0,
                borderBottomWidth: pos.includes("bottom") ? "3px" : 0,
              }}
            />
          ))}
        </motion.div>
      )}
    </div>
  );
}

type GridOverlayProps = {
  visible: boolean;
  frame: Frame;
  aspect: Aspect;
};

export function GridOverlay({ visible, frame, aspect }: GridOverlayProps) {
  return (
    <AnimatePresence>
      {visible && frame.w > 10 && frame.h > 10 && (
        <motion.div
          key={`grid-${aspect}`}
          className="pointer-events-none absolute"
          style={{
            width: `${frame.w}px`,
            height: `${frame.h}px`,
            left: `${frame.left}px`,
            top: `${frame.top}px`,
          }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25, ease: "easeInOut" }}
        >
          <div className="grid h-full w-full grid-cols-3 grid-rows-3">
            {Array.from({ length: 9 }).map((_, i) => (
              <motion.div
                key={i}
                className={`border-white/25 ${i % 3 !== 0 ? "border-l" : ""} ${
                  i >= 3 ? "border-t" : ""
                }`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: i * 0.02, duration: 0.2 }}
              />
            ))}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

type ThumbnailPreviewProps = {
  imageUrl: string | null;
  onOpen: () => void;
};

export function ThumbnailPreview({ imageUrl, onOpen }: ThumbnailPreviewProps) {
  if (!imageUrl) return null;

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    vibrate([10]);
    onOpen();
  };

  return (
    <motion.button
      type="button"
      onClick={handleClick}
      aria-label="Открыть последнее фото"
      className="pointer-events-auto absolute bottom-28 right-4 z-[10005] h-20 w-20 overflow-hidden rounded-2xl bg-black/40 shadow-2xl ring-[3px] ring-white/60 backdrop-blur-sm transition-all hover:ring-white/80 focus:outline-none focus-visible:ring-4 focus-visible:ring-white active:scale-95 touch-none"
      initial={{ opacity: 0, y: 20, scale: 0.8 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 20, scale: 0.8 }}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      title="Открыть последнее фото"
      style={{ WebkitTapHighlightColor: "transparent" }}
    >
      <img
        src={imageUrl}
        alt="Последний кадр"
        className="w-full h-full object-cover pointer-events-none"
        draggable={false}
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/30 to-transparent pointer-events-none" />
    </motion.button>
  );
}

export function ErrorDisplay({
  error,
  onClose,
}: {
  error: string | null;
  onClose: () => void;
}) {
  return (
    <AnimatePresence>
      {error && (
        <motion.div
          className="absolute inset-0 grid place-items-center p-6 bg-black/60 backdrop-blur-md z-50"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.div
            className="rounded-[20px] bg-gradient-to-b from-rose-500/95 to-rose-600/95 backdrop-blur-2xl px-6 py-5 text-white text-center max-w-sm shadow-[0_0_0_1px_rgba(255,255,255,0.2)_inset,0_8px_32px_rgba(0,0,0,0.4)]"
            initial={{ scale: 0.9, y: 20 }}
            animate={{ scale: 1, y: 0 }}
          >
            <FaExclamationTriangle
              className="mx-auto mb-3 drop-shadow-lg"
              size={48}
            />
            <p className="font-semibold text-[15px]">{error}</p>
            <button
              type="button"
              onClick={onClose}
              className="mt-4 px-5 py-2.5 rounded-[14px] bg-white/20 hover:bg-white/30 active:bg-white/15 transition-colors text-sm font-medium shadow-[0_0_0_1px_rgba(255,255,255,0.15)_inset] focus:outline-none focus-visible:ring-4 focus-visible:ring-white/70"
            >
              Закрыть
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function FullscreenPreview({
  imageUrl,
  onClose,
}: {
  imageUrl: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const handleClose = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onClose();
  };

  return (
    <motion.div
      className="fixed inset-0 z-[10020] bg-black/90 flex items-center justify-center p-4 cursor-pointer touch-none"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      onClick={handleClose}
      style={{ WebkitTapHighlightColor: "transparent" }}
    >
      <motion.img
        src={imageUrl}
        alt="Снимок"
        className="max-w-[96vw] max-h-[88dvh] object-contain rounded-xl shadow-2xl select-none pointer-events-none touch-none"
        initial={{ scale: 0.5, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.5, opacity: 0 }}
        transition={{
          type: "spring",
          stiffness: 280,
          damping: 24,
          opacity: { duration: 0.2 },
        }}
        draggable={false}
      />

      <motion.button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          handleClose(e);
        }}
        aria-label="Закрыть предпросмотр"
        className="absolute top-4 right-4 p-2.5 rounded-full bg-black/40 ring-1 ring-white/20 backdrop-blur-xl text-white hover:bg-black/60 active:bg-black/50 transition-all shadow-2xl z-10 touch-none focus:outline-none focus-visible:ring-4 focus-visible:ring-white/70"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        title="Закрыть"
        style={{ WebkitTapHighlightColor: "transparent" }}
      >
        <FaTimesCircle size={24} />
      </motion.button>
    </motion.div>
  );
}
