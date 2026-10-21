type Size = { w: number; h: number };

export function ovalInFrame(frame: Size) {
  const rx = Math.min(frame.w * 0.38, frame.h * 0.27);
  return { cx: frame.w / 2, cy: frame.h * 0.47, rx, ry: rx * 1.3 };
}

export type VideoBox = { x: number; y: number; w: number; h: number };

export function screenBoxToVideo(
  box: { left: number; top: number; w: number; h: number },
  display: Size,
  video: Size,
  mirrored: boolean,
): VideoBox {
  const s = Math.max(display.w / video.w, display.h / video.h);
  const offX = (display.w - video.w * s) / 2;
  const offY = (display.h - video.h * s) / 2;
  const w = box.w / s / video.w;
  const x = (box.left - offX) / s / video.w;
  return {
    x: mirrored ? 1 - x - w : x,
    y: (box.top - offY) / s / video.h,
    w,
    h: box.h / s / video.h,
  };
}
