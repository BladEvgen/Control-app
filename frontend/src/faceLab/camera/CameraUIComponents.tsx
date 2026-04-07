import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FaTimesCircle, FaExclamationTriangle } from "react-icons/fa";
import type { Aspect, CameraGuidanceContext, Frame } from "./types";
import { cameraGuidanceMessage } from "./cameraGuidanceMessage";
import { vibrate } from "./camera-utils";

export function CameraGuidanceBanner({
  context,
  requireLiveness,
}: {
  context: CameraGuidanceContext;
  requireLiveness: boolean;
}) {
  const text = cameraGuidanceMessage(context, requireLiveness);
  return (
    <div
      className="pointer-events-none max-w-lg rounded-2xl bg-black/45 px-4 py-2.5 text-center text-sm font-medium leading-snug text-white shadow-lg ring-1 ring-white/15 backdrop-blur-md sm:max-w-xl sm:text-[0.95rem] [text-shadow:0_1px_3px_rgba(0,0,0,0.85)]"
      role="status"
    >
      {text}
    </div>
  );
}

type CircleBtnProps = {
  title?: string;
  onClick?: (e?: React.PointerEvent) => void;
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

  const handleClick = (e: React.PointerEvent) => {
    if (disabled || !onClick) return;
    e.preventDefault();
    e.stopPropagation();
    vibrate([10]);
    onClick(e);
  };

  return (
    <motion.button
      type="button"
      title={title}
      aria-label={title}
      disabled={disabled}
      onPointerDown={handleClick}
      whileHover={{ scale: disabled ? 1 : 1.08 }}
      whileTap={{ scale: disabled ? 1 : 0.92 }}
      className={`inline-flex items-center justify-center rounded-full ring-2 transition-all duration-200 focus:outline-none focus:ring-4 touch-none ${theme} ${
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

function ViewfinderFrontPoseSchematic() {
  return (
    <div className="flex flex-col items-center">
      <svg
        viewBox="0 0 88 104"
        className="h-[min(26vw,6.5rem)] w-[min(26vw,6.5rem)] max-h-[108px] max-w-[108px] drop-shadow-[0_4px_14px_rgba(0,0,0,0.55)] sm:h-[7.25rem] sm:w-[7.25rem] sm:max-h-none sm:max-w-none"
        aria-hidden
      >
        <motion.g
          animate={{ scale: [1, 1.04, 1], opacity: [0.88, 1, 0.88] }}
          transition={{
            duration: 2.6,
            repeat: Infinity,
            ease: "easeInOut",
          }}
          style={{ transformOrigin: "44px 52px" }}
        >
          <ellipse
            cx="44"
            cy="46"
            rx="28"
            ry="34"
            fill="rgba(255,255,255,0.14)"
            stroke="rgba(255,255,255,0.88)"
            strokeWidth="2.2"
          />
          <circle cx="34" cy="42" r="3" fill="rgba(255,255,255,0.9)" />
          <circle cx="54" cy="42" r="3" fill="rgba(255,255,255,0.9)" />
          <path
            d="M44 52 L38 62 L50 62 Z"
            fill="rgba(255,255,255,0.35)"
            stroke="rgba(255,255,255,0.5)"
            strokeWidth="0.8"
          />
          <line
            x1="44"
            y1="66"
            x2="44"
            y2="78"
            stroke="rgba(255,255,255,0.55)"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </motion.g>
      </svg>
    </div>
  );
}

function FaceFrontSvg({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 88 100" className={className} aria-hidden>
      <ellipse
        cx="44"
        cy="44"
        rx="28"
        ry="34"
        fill="rgba(255,255,255,0.92)"
        stroke="rgba(30,30,30,0.2)"
        strokeWidth="1.8"
      />
      <circle cx="34" cy="40" r="3.2" fill="rgba(0,0,0,0.35)" />
      <circle cx="54" cy="40" r="3.2" fill="rgba(0,0,0,0.35)" />
      <path
        d="M44 50 L38 60 L50 60 Z"
        fill="rgba(0,0,0,0.22)"
        stroke="rgba(0,0,0,0.15)"
        strokeWidth="0.6"
      />
      <line
        x1="44"
        y1="64"
        x2="44"
        y2="78"
        stroke="rgba(0,0,0,0.2)"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ProfileYawSwing({ direction }: { direction: "left" | "right" }) {
  const rot = direction === "left" ? [0, -18, 0] : [0, 18, 0];
  return (
    <div className="flex flex-col items-center border-t border-white/15 pt-2">
      <p
        className="mb-1 text-[8px] font-medium uppercase tracking-wide text-white/70 sm:text-[9px]"
        style={{ fontFamily: "system-ui, sans-serif" }}
      >
        вид сбоку — тот же поворот
      </p>
      <svg
        viewBox="0 0 72 56"
        className="h-11 w-[4.5rem] sm:h-12 sm:w-[4.75rem]"
        aria-hidden
      >
        <motion.g
          style={{ transformOrigin: "36px 48px" }}
          animate={{ rotate: rot }}
          transition={{
            duration: 2.35,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        >
          <path
            d="M 14 48 L 14 26 Q 14 12 30 10 L 44 12 Q 52 16 54 26 L 54 48"
            fill="rgba(255,255,255,0.14)"
            stroke="rgba(255,255,255,0.9)"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
          <path
            d="M 52 22 Q 58 20 60 24"
            fill="none"
            stroke="rgba(255,255,255,0.55)"
            strokeWidth="1.2"
            strokeLinecap="round"
          />
        </motion.g>
      </svg>
    </div>
  );
}

function ViewfinderYawTurnFace3D({
  direction,
}: {
  direction: "left" | "right";
}) {
  const yDeg = direction === "left" ? -22 : 22;
  return (
    <div className="flex max-w-[min(92%,280px)] flex-col items-center gap-2">
      <div
        className="relative flex h-[min(30vw,7.5rem)] w-[min(30vw,7.5rem)] min-h-[104px] min-w-[104px] items-center justify-center sm:h-32 sm:w-32"
        style={{
          perspective: "280px",
          perspectiveOrigin: "50% 42%",
        }}
      >
        <div
          className="pointer-events-none absolute inset-0 flex items-center justify-center"
          aria-hidden
        >
          <FaceFrontSvg className="h-full w-full opacity-[0.2] saturate-0" />
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
          <FaceFrontSvg className="h-full w-full drop-shadow-[0_8px_22px_rgba(0,0,0,0.5)]" />
        </motion.div>
      </div>

      <ProfileYawSwing direction={direction} />

      <div className="text-center leading-tight">
        <p
          className="text-[10px] font-semibold text-white [text-shadow:0_1px_4px_rgba(0,0,0,0.9)] sm:text-[11px]"
          style={{ fontFamily: "system-ui, sans-serif" }}
        >
          Поворот головы — лицо уходит «вглубь» экрана
        </p>
        <p
          className="mt-1 text-[9px] text-white/85 [text-shadow:0_1px_3px_rgba(0,0,0,0.85)] sm:text-[10px]"
          style={{ fontFamily: "system-ui, sans-serif" }}
        >
          не наклон влево-вправо ухом
        </p>
        <p
          className="mt-1.5 text-[10px] font-bold text-white sm:text-xs"
          style={{ fontFamily: "system-ui, sans-serif" }}
        >
          ≈20°
        </p>
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
        <div className="flex h-full w-full flex-col items-center justify-between px-2 pb-[6%] pt-[5%]">
          <motion.div
            animate={{ opacity: [0.75, 1, 0.75] }}
            transition={{
              duration: 2.4,
              repeat: Infinity,
              ease: "easeInOut",
            }}
            className="max-w-[94%] rounded-2xl bg-black/58 px-3 py-2 text-center text-xs font-semibold leading-snug text-white shadow-lg ring-1 ring-white/35 backdrop-blur-md sm:px-4 sm:text-sm"
          >
            Совместите лицо с макетом — анфас
          </motion.div>
          <ViewfinderFrontPoseSchematic />
        </div>
      </div>
    );
  }

  if (context === "profile_photo") {
    return (
      <div className="pointer-events-none absolute z-[26]" style={boxStyle}>
        <div className="flex h-full w-full flex-col items-center justify-between px-2 pb-[6%] pt-[5%]">
          <motion.div
            animate={{ opacity: [0.75, 1, 0.75] }}
            transition={{
              duration: 2.6,
              repeat: Infinity,
              ease: "easeInOut",
            }}
            className="max-w-[94%] rounded-2xl bg-black/58 px-3 py-2 text-center text-xs font-semibold leading-snug text-white shadow-lg ring-1 ring-white/35 backdrop-blur-md sm:px-4 sm:text-sm"
          >
            Совместите лицо с макетом — фото для карточки
          </motion.div>
          <ViewfinderFrontPoseSchematic />
        </div>
      </div>
    );
  }

  if (context === "bootstrap_left" || context === "bootstrap_right") {
    const toLeft = context === "bootstrap_left";
    return (
      <div className="pointer-events-none absolute z-[26]" style={boxStyle}>
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 px-2">
          <ViewfinderYawTurnFace3D direction={toLeft ? "left" : "right"} />
          <span className="max-w-[96%] rounded-2xl bg-black/60 px-3 py-2 text-center text-xs font-semibold leading-tight text-white ring-1 ring-white/35 backdrop-blur-md sm:text-sm">
            {toLeft
              ? "Повторите разворот лица влево, как на анимации (не наклоняйте голову вбок)"
              : "Повторите разворот лица вправо, как на анимации (не наклоняйте голову вбок)"}
          </span>
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

export function FlashEffect({ visible }: { visible: boolean }) {
  const [mounted, setMounted] = useState(false);
  const [lit, setLit] = useState(false);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (hideTimerRef.current != null) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }

    if (visible) {
      setMounted(true);
      setLit(false);
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = requestAnimationFrame(() => {
          rafRef.current = null;
          setLit(true);
        });
      });
      return () => {
        if (rafRef.current != null) {
          cancelAnimationFrame(rafRef.current);
          rafRef.current = null;
        }
      };
    }

    setLit(false);
    hideTimerRef.current = setTimeout(() => {
      hideTimerRef.current = null;
      setMounted(false);
    }, 240);
    return () => {
      if (hideTimerRef.current != null) {
        clearTimeout(hideTimerRef.current);
        hideTimerRef.current = null;
      }
    };
  }, [visible]);

  if (!mounted) return null;

  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-[10012] isolate bg-white will-change-[opacity]"
      style={{
        opacity: lit ? 1 : 0,
        transform: "translateZ(0)",
        backfaceVisibility: "hidden",
        transition: lit
          ? "opacity 95ms cubic-bezier(0.22, 1, 0.36, 1)"
          : "opacity 220ms cubic-bezier(0.4, 0, 0.2, 1)",
      }}
    />
  );
}

type ThumbnailPreviewProps = {
  imageUrl: string | null;
  onOpen: () => void;
};

export function ThumbnailPreview({ imageUrl, onOpen }: ThumbnailPreviewProps) {
  if (!imageUrl) return null;

  const handleClick = (e: React.PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    vibrate([10]);
    onOpen();
  };

  return (
    <motion.button
      type="button"
      onPointerDown={handleClick}
      className="pointer-events-auto absolute bottom-28 right-4 z-[10005] h-20 w-20 overflow-hidden rounded-2xl bg-black/40 shadow-2xl ring-[3px] ring-white/60 backdrop-blur-sm transition-all hover:ring-white/80 active:scale-95 touch-none"
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
              className="mt-4 px-5 py-2.5 rounded-[14px] bg-white/20 hover:bg-white/30 active:bg-white/15 transition-colors text-sm font-medium shadow-[0_0_0_1px_rgba(255,255,255,0.15)_inset]"
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
  const handleClose = (e: React.MouseEvent | React.PointerEvent) => {
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
      onPointerDown={handleClose}
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
        onPointerDown={(e) => {
          e.stopPropagation();
          handleClose(e);
        }}
        className="absolute top-4 right-4 p-2.5 rounded-full bg-black/40 ring-1 ring-white/20 backdrop-blur-xl text-white hover:bg-black/60 active:bg-black/50 transition-all shadow-2xl z-10 touch-none"
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
