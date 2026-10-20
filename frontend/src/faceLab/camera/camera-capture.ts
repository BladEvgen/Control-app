import type { Frame } from "./types";
import { camLog } from "./cameraLog";
import { laplacianVariance } from "./sharpness";

export type CaptureOptions = {
  video: HTMLVideoElement;
  frame: Frame;
  container: HTMLDivElement;
  shouldMirror: boolean;
  maxWidth?: number;
  maxHeight?: number;
  quality?: number;
  shots?: number;
};

export function waitForVideoPipelineFrames(
  video: HTMLVideoElement,
  count: number,
): Promise<void> {
  if (count <= 0) return Promise.resolve();
  const rvfc = video.requestVideoFrameCallback?.bind(video);
  if (rvfc) {
    return new Promise((resolve) => {
      let left = count;
      const onFrame: VideoFrameRequestCallback = () => {
        left -= 1;
        if (left <= 0) resolve();
        else rvfc(onFrame);
      };
      rvfc(onFrame);
    });
  }
  return new Promise((r) => void setTimeout(r, Math.max(40, count * 34)));
}

type DrawCroppedOptions = {
  source: CanvasImageSource;
  sourceWidth: number;
  sourceHeight: number;
  video: HTMLVideoElement;
  frame: Frame;
  container: HTMLDivElement;
  shouldMirror: boolean;
  maxLong: number;
};

function canvasSharpness(canvas: HTMLCanvasElement): number {
  const w = 192;
  const h = Math.max(1, Math.round((canvas.height / canvas.width) * w));
  const small = document.createElement("canvas");
  small.width = w;
  small.height = h;
  const ctx = small.getContext("2d", { willReadFrequently: true });
  if (!ctx) return 0;
  ctx.drawImage(canvas, 0, 0, w, h);
  return laplacianVariance(ctx.getImageData(0, 0, w, h).data, w, h);
}

function drawCropped(options: DrawCroppedOptions): HTMLCanvasElement | null {
  const {
    source,
    sourceWidth,
    sourceHeight,
    video,
    frame,
    container,
    shouldMirror,
    maxLong,
  } = options;

  if (!frame.w || !frame.h) {
    camLog.info("Frame not ready");
    return null;
  }

  camLog.info("Capturing", {
    sourceResolution: `${sourceWidth}x${sourceHeight}`,
  });

  const containerRect = container.getBoundingClientRect();
  const videoRect = video.getBoundingClientRect();

  const videoAspect = sourceWidth / sourceHeight;
  const displayAspect = videoRect.width / videoRect.height;

  let actualVideoWidth: number;
  let actualVideoHeight: number;
  let videoOffsetX = 0;
  let videoOffsetY = 0;

  if (videoAspect > displayAspect) {
    actualVideoHeight = videoRect.height;
    actualVideoWidth = videoRect.height * videoAspect;
    videoOffsetX = (actualVideoWidth - videoRect.width) / 2;
  } else {
    actualVideoWidth = videoRect.width;
    actualVideoHeight = videoRect.width / videoAspect;
    videoOffsetY = (actualVideoHeight - videoRect.height) / 2;
  }

  const scaleX = sourceWidth / actualVideoWidth;
  const scaleY = sourceHeight / actualVideoHeight;

  const frameLeft = frame.left - (videoRect.left - containerRect.left);
  const frameTop = frame.top - (videoRect.top - containerRect.top);

  const cropX = (frameLeft + videoOffsetX) * scaleX;
  const cropY = (frameTop + videoOffsetY) * scaleY;
  const cropWidth = frame.w * scaleX;
  const cropHeight = frame.h * scaleY;

  const cropW = Math.round(cropWidth);
  const cropH = Math.round(cropHeight);
  const longEdge = Math.max(cropW, cropH);
  let finalWidth = cropW;
  let finalHeight = cropH;
  if (longEdge > maxLong) {
    const scale = maxLong / longEdge;
    finalWidth = Math.round(cropW * scale);
    finalHeight = Math.round(cropH * scale);
    camLog.info("Downscaling to max long edge", `${finalWidth}x${finalHeight}`);
  }

  const canvas = document.createElement("canvas");
  canvas.width = finalWidth;
  canvas.height = finalHeight;

  const ctx = canvas.getContext("2d", {
    alpha: false,
    desynchronized: true,
  });

  if (!ctx) {
    camLog.info("Failed to get canvas context");
    return null;
  }

  if (shouldMirror) {
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
  }

  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";

  ctx.drawImage(
    source,
    Math.max(0, cropX),
    Math.max(0, cropY),
    cropWidth,
    cropHeight,
    0,
    0,
    canvas.width,
    canvas.height,
  );

  return canvas;
}

function toJpeg(
  canvas: HTMLCanvasElement,
  quality: number,
): Promise<Blob | null> {
  return new Promise<Blob | null>((resolve) => {
    canvas.toBlob(
      (blob) => {
        if (blob) {
          camLog.info("Photo captured", {
            finalSize: `${canvas.width}x${canvas.height}`,
            kb: (blob.size / 1024).toFixed(0),
          });
        }
        resolve(blob);
      },
      "image/jpeg",
      quality,
    );
  });
}

export async function capturePhoto(
  options: CaptureOptions,
): Promise<Blob | null> {
  const {
    video,
    frame,
    container,
    shouldMirror,
    maxWidth = 4096,
    maxHeight = 4096,
    quality = 0.95,
    shots = 3,
  } = options;

  const videoWidth = video.videoWidth;
  const videoHeight = video.videoHeight;

  if (!videoWidth || !videoHeight) {
    camLog.info("Video dimensions not available");
    return null;
  }

  const maxLong = Math.max(maxWidth, maxHeight);

  let best: HTMLCanvasElement | null = null;
  let bestScore = -1;
  for (let i = 0; i < shots; i += 1) {
    if (i > 0) await waitForVideoPipelineFrames(video, 1);
    const canvas = drawCropped({
      source: video,
      sourceWidth: videoWidth,
      sourceHeight: videoHeight,
      video,
      frame,
      container,
      shouldMirror,
      maxLong,
    });
    if (!canvas) continue;
    const score = shots > 1 ? canvasSharpness(canvas) : 0;
    if (score > bestScore) {
      best = canvas;
      bestScore = score;
    }
  }
  return best ? toJpeg(best, quality) : null;
}
