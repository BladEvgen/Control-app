import type { Frame } from "./types";
import { camLog } from "./cameraLog";

export type CaptureOptions = {
  video: HTMLVideoElement;
  track?: MediaStreamTrack | null;
  frame: Frame;
  container: HTMLDivElement;
  shouldMirror: boolean;
  maxWidth?: number;
  maxHeight?: number;
  quality?: number;
  preferStillCapture?: boolean;
};

type ImageCaptureLike = {
  takePhoto?: (settings?: Record<string, unknown>) => Promise<Blob>;
  grabFrame?: () => Promise<ImageBitmap>;
  getPhotoCapabilities?: () => Promise<{
    imageWidth?: { max?: number; min?: number };
    imageHeight?: { max?: number; min?: number };
    fillLightMode?: string[];
  }>;
};

type ImageCaptureCtor = new (track: MediaStreamTrack) => ImageCaptureLike;

function imageCaptureCtor(): ImageCaptureCtor | null {
  const win = window as unknown as { ImageCapture?: ImageCaptureCtor };
  return typeof win.ImageCapture === "function" ? win.ImageCapture : null;
}

function withTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number,
): Promise<T | null> {
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => resolve(null), timeoutMs);
    promise
      .then((value) => {
        window.clearTimeout(timer);
        resolve(value);
      })
      .catch(() => {
        window.clearTimeout(timer);
        resolve(null);
      });
  });
}

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
  quality: number;
};

async function drawCroppedJpeg(
  options: DrawCroppedOptions,
): Promise<Blob | null> {
  const {
    source,
    sourceWidth,
    sourceHeight,
    video,
    frame,
    container,
    shouldMirror,
    maxLong,
    quality,
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

  return new Promise<Blob | null>((resolve) => {
    canvas.toBlob(
      (blob) => {
        if (blob) {
          camLog.info("Photo captured", {
            finalSize: `${finalWidth}x${finalHeight}`,
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

async function captureImageCaptureStill(
  track: MediaStreamTrack | null | undefined,
): Promise<{ source: ImageBitmap; sourceName: string } | null> {
  if (!track) return null;
  const Ctor = imageCaptureCtor();
  if (!Ctor) return null;

  try {
    const ic = new Ctor(track);
    if (typeof ic.grabFrame === "function") {
      const bitmap = await withTimeout(ic.grabFrame(), 220);
      if (!bitmap) return null;
      return { source: bitmap, sourceName: "ImageCapture.grabFrame" };
    }
  } catch {
    return null;
  }

  return null;
}

export async function capturePhoto(
  options: CaptureOptions,
): Promise<Blob | null> {
  const {
    video,
    track,
    frame,
    container,
    shouldMirror,
    maxWidth = 2560,
    maxHeight = 2560,
    quality = 0.96,
    preferStillCapture = false,
  } = options;

  const videoWidth = video.videoWidth;
  const videoHeight = video.videoHeight;

  if (!videoWidth || !videoHeight) {
    camLog.info("Video dimensions not available");
    return null;
  }

  const maxLong = Math.max(maxWidth, maxHeight);
  const still = preferStillCapture
    ? await captureImageCaptureStill(track)
    : null;
  if (still) {
    camLog.info("Using camera still source", {
      source: still.sourceName,
      size: `${still.source.width}x${still.source.height}`,
    });
    try {
      return await drawCroppedJpeg({
        source: still.source,
        sourceWidth: still.source.width,
        sourceHeight: still.source.height,
        video,
        frame,
        container,
        shouldMirror,
        maxLong,
        quality,
      });
    } finally {
      still.source.close();
    }
  }

  return drawCroppedJpeg({
    source: video,
    sourceWidth: videoWidth,
    sourceHeight: videoHeight,
    video,
    frame,
    container,
    shouldMirror,
    maxLong,
    quality,
  });
}

export function createPreviewUrl(
  video: HTMLVideoElement,
  frame: Frame,
  container: HTMLDivElement,
  shouldMirror: boolean,
): string | null {
  const canvas = document.createElement("canvas");
  const videoWidth = video.videoWidth || 1920;
  const videoHeight = video.videoHeight || 1080;

  const containerRect = container.getBoundingClientRect();
  const videoRect = video.getBoundingClientRect();

  const videoAspect = videoWidth / videoHeight;
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

  const scaleX = videoWidth / actualVideoWidth;
  const scaleY = videoHeight / actualVideoHeight;

  const frameLeft = frame.left - (videoRect.left - containerRect.left);
  const frameTop = frame.top - (videoRect.top - containerRect.top);

  const cropX = (frameLeft + videoOffsetX) * scaleX;
  const cropY = (frameTop + videoOffsetY) * scaleY;
  const cropWidth = frame.w * scaleX;
  const cropHeight = frame.h * scaleY;

  const previewWidth = Math.min(640, Math.round(cropWidth));
  const previewHeight = Math.round(previewWidth / (cropWidth / cropHeight));

  canvas.width = previewWidth;
  canvas.height = previewHeight;

  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  if (shouldMirror) {
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
  }

  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";

  ctx.drawImage(
    video,
    Math.max(0, cropX),
    Math.max(0, cropY),
    cropWidth,
    cropHeight,
    0,
    0,
    canvas.width,
    canvas.height,
  );

  return canvas.toDataURL("image/jpeg", 0.85);
}
