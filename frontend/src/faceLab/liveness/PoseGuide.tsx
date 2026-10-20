import { memo, useId } from "react";
import { MotionConfig, motion, type Transition } from "framer-motion";

export type PoseGuidePose =
  | "front"
  | "turn_left"
  | "turn_right"
  | "blink"
  | "smile"
  | "mouth_open"
  | "hold"
  | "done";

type Props = {
  pose: PoseGuidePose;
  progress?: number | null;
  size?: number;
  className?: string;
  label?: string;
  animate?: boolean;
};

const MOUTH_FLAT = "M52 80 Q60 81 68 80";
const MOUTH_SMILE = "M50 78 Q60 88 70 78";
const TURN_DX = 9;

const loop = (duration: number, extra: Transition = {}): Transition => ({
  duration,
  repeat: Infinity,
  ease: "easeInOut",
  ...extra,
});

const box = { transformBox: "fill-box", transformOrigin: "center" } as const;

export function PoseGuide({
  pose,
  progress = null,
  size = 96,
  className = "",
  label,
  animate = true,
}: Props) {
  const ring = progress === null ? null : Math.min(1, Math.max(0, progress));
  return (
    <MotionConfig reducedMotion="never">
      <svg
        viewBox="0 0 120 120"
        width={size}
        height={size}
        className={className}
        role={label ? "img" : undefined}
        aria-label={label}
        aria-hidden={label ? undefined : true}
      >
        <circle
          cx="60"
          cy="60"
          r="56"
          fill="none"
          stroke="currentColor"
          strokeOpacity="0.14"
          strokeWidth="3"
        />
        {ring !== null ? (
          <motion.circle
            cx="60"
            cy="60"
            r="56"
            fill="none"
            stroke="currentColor"
            strokeWidth="3.5"
            strokeLinecap="round"
            transform="rotate(-90 60 60)"
            initial={false}
            animate={{ pathLength: ring, opacity: ring > 0 ? 1 : 0 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
          />
        ) : null}
        <PoseFigure pose={pose} still={!animate} />
      </svg>
    </MotionConfig>
  );
}

const PoseFigure = memo(function PoseFigure({
  pose,
  still,
}: {
  pose: PoseGuidePose;
  still: boolean;
}) {
  const clipId = useId();
  const turn = pose === "turn_left" ? -1 : pose === "turn_right" ? 1 : 0;
  const dx = turn * TURN_DX;

  const featuresAnim = turn
    ? still
      ? { x: dx }
      : { x: [0, dx, dx, 0] }
    : { x: 0 };
  const featuresTr: Transition =
    turn && !still
      ? loop(2.6, { times: [0, 0.35, 0.7, 1] })
      : { duration: 0.3 };

  const ear = (cx: number, hides: boolean) => {
    const to = { cx: cx + dx * 0.3, opacity: hides ? 0.2 : 1 };
    if (!turn || still) return to;
    return {
      cx: [cx, to.cx, to.cx, cx],
      opacity: [1, to.opacity, to.opacity, 1],
    };
  };

  const headAnim =
    pose === "front" && !still
      ? { x: [-7, 0, 0], y: [4, 0, 0] }
      : { x: 0, y: 0 };
  const headTr: Transition =
    pose === "front" && !still
      ? loop(2.6, { times: [0, 0.4, 1], ease: "easeOut" })
      : { duration: 0.3 };

  const eyeAnim =
    pose === "blink"
      ? still
        ? { scaleY: 0.15 }
        : { scaleY: [1, 1, 0.12, 1] }
      : { scaleY: 1 };
  const eyeTr: Transition =
    pose === "blink" && !still
      ? loop(1.8, { times: [0, 0.55, 0.65, 0.8], ease: "easeOut" })
      : { duration: 0.2 };

  const mouthD =
    pose === "smile"
      ? still
        ? MOUTH_SMILE
        : [MOUTH_FLAT, MOUTH_SMILE, MOUTH_SMILE, MOUTH_FLAT]
      : MOUTH_FLAT;
  const mouthTr: Transition =
    pose === "smile" && !still
      ? loop(2.2, { times: [0, 0.35, 0.75, 1] })
      : { duration: 0.3 };

  const mouthOpen = pose === "mouth_open";

  return (
    <>
      {pose === "front" || pose === "hold" ? (
        <motion.ellipse
          cx="60"
          cy="62"
          rx="34"
          ry="41"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeDasharray={pose === "front" ? "5 5" : undefined}
          style={box}
          animate={
            still
              ? { opacity: 0.4, scale: 1 }
              : pose === "front"
                ? { opacity: [0.2, 0.75, 0.75], scale: [1.12, 1, 1] }
                : { opacity: [0.15, 0.6, 0.15], scale: [1, 1.04, 1] }
          }
          transition={
            still
              ? { duration: 0.3 }
              : pose === "front"
                ? loop(2.6, { times: [0, 0.4, 1], ease: "easeOut" })
                : loop(1.4)
          }
        />
      ) : null}

      <clipPath id={clipId}>
        <circle cx="60" cy="60" r="53" />
      </clipPath>
      <motion.g
        clipPath={`url(#${clipId})`}
        animate={headAnim}
        transition={headTr}
      >
        <path
          d="M34 116 C36 100 47 95 60 95 C73 95 84 100 86 116"
          fill="currentColor"
          fillOpacity="0.1"
          stroke="currentColor"
          strokeOpacity="0.55"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
        <motion.ellipse
          cy="63"
          rx="4"
          ry="8"
          fill="currentColor"
          fillOpacity="0.25"
          animate={ear(33, turn < 0)}
          transition={featuresTr}
        />
        <motion.ellipse
          cy="63"
          rx="4"
          ry="8"
          fill="currentColor"
          fillOpacity="0.25"
          animate={ear(87, turn > 0)}
          transition={featuresTr}
        />
        <ellipse
          cx="60"
          cy="62"
          rx="27"
          ry="33"
          fill="currentColor"
          fillOpacity="0.1"
          stroke="currentColor"
          strokeWidth="2.5"
        />
        <path
          d="M33 54 C33 26 87 26 87 54 C79 40 41 40 33 54Z"
          fill="currentColor"
          fillOpacity="0.4"
        />

        <motion.g animate={featuresAnim} transition={featuresTr}>
          <path
            d="M45 52 Q50 49 55 52 M65 52 Q70 49 75 52"
            fill="none"
            stroke="currentColor"
            strokeOpacity="0.6"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <motion.ellipse
            cx="50"
            cy="60"
            rx="3.4"
            ry="3.4"
            fill="currentColor"
            style={box}
            animate={eyeAnim}
            transition={eyeTr}
          />
          <motion.ellipse
            cx="70"
            cy="60"
            rx="3.4"
            ry="3.4"
            fill="currentColor"
            style={box}
            animate={eyeAnim}
            transition={eyeTr}
          />
          <path
            d="M60 63 L57 72 Q60 73.5 62 72"
            fill="none"
            stroke="currentColor"
            strokeOpacity="0.7"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {mouthOpen ? (
            <motion.ellipse
              cx="60"
              cy="81"
              rx="6"
              fill="currentColor"
              fillOpacity="0.85"
              animate={still ? { ry: 5 } : { ry: [1, 6, 6, 1] }}
              transition={
                still
                  ? { duration: 0.3 }
                  : loop(2, { times: [0, 0.35, 0.7, 1] })
              }
            />
          ) : (
            <motion.path
              d={MOUTH_FLAT}
              fill="none"
              stroke="currentColor"
              strokeWidth="2.6"
              strokeLinecap="round"
              animate={{ d: mouthD }}
              transition={mouthTr}
            />
          )}
        </motion.g>
      </motion.g>

      {turn ? (
        <motion.path
          d={
            turn < 0
              ? "M78 16 Q60 9 42 16 M42 16 l7 -5 M42 16 l6 6"
              : "M42 16 Q60 9 78 16 M78 16 l-7 -5 M78 16 l-6 6"
          }
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
          animate={
            still
              ? { pathLength: 1, opacity: 1 }
              : { pathLength: [0, 1, 1], opacity: [0, 1, 0] }
          }
          transition={
            still
              ? { duration: 0 }
              : loop(2.6, { times: [0, 0.35, 1], ease: "easeOut" })
          }
        />
      ) : null}

      {pose === "done" ? (
        <motion.g
          initial={{ scale: 0.4, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          style={box}
          transition={{ type: "spring", stiffness: 420, damping: 22 }}
        >
          <circle cx="92" cy="92" r="14" fill="currentColor" />
          <path
            d="M85 92 l5 5 l9 -10"
            fill="none"
            stroke="var(--pose-guide-check, #10b981)"
            strokeWidth="3.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </motion.g>
      ) : null}
    </>
  );
});
