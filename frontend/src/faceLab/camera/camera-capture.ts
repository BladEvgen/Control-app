import type { Frame } from "./types";
import { camLog } from "./cameraLog";

export type CaptureOptions = {
  video: HTMLVideoElement;
  frame: Frame;
  container: HTMLDivElement;
  shouldMirror: boolean;
  maxWidth?: number;
  maxHeight?: number;
  quality?: number;
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

export async function capturePhoto(
  options: CaptureOptions,
): Promise<Blob | null> {
  const {
    video,
    frame,
    container,
    shouldMirror,
    maxWidth = 1280,
    maxHeight = 1280,
    quality = 0.88,
  } = options;

  const videoWidth = video.videoWidth;
  const videoHeight = video.videoHeight;

  if (!videoWidth || !videoHeight) {
    camLog.info("Video dimensions not available");
    return null;
  }

  if (!frame.w || !frame.h) {
    camLog.info("Frame not ready");
    return null;
  }

  camLog.info("Capturing", {
    videoResolution: `${videoWidth}x${videoHeight}`,
  });

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

  const maxLong = Math.max(maxWidth, maxHeight);
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
