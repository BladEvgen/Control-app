import { useState, useCallback, useEffect } from "react";
import type { Aspect, Frame } from "./types";
import { getAspectRatio } from "./camera-utils";

export function useCameraFrame(
  aspect: Aspect,
  containerRef: React.RefObject<HTMLDivElement | null>,
  videoRef: React.RefObject<HTMLVideoElement | null>,
) {
  const [frame, setFrame] = useState<Frame>({
    w: 0,
    h: 0,
    left: 0,
    top: 0,
  });

  const aspectRatio = getAspectRatio(aspect);

  const recomputeFrame = useCallback(() => {
    const container = containerRef.current;
    const video = videoRef.current;

    if (!container || !video) return;

    const containerRect = container.getBoundingClientRect();
    const videoRect = video.getBoundingClientRect();

    const videoDisplayWidth = videoRect.width;
    const videoDisplayHeight = videoRect.height;

    let frameWidth = videoDisplayWidth;
    let frameHeight = frameWidth / aspectRatio;

    if (frameHeight > videoDisplayHeight) {
      frameHeight = videoDisplayHeight;
      frameWidth = frameHeight * aspectRatio;
    }

    const left =
      videoRect.left -
      containerRect.left +
      (videoDisplayWidth - frameWidth) / 2;
    const top =
      videoRect.top -
      containerRect.top +
      (videoDisplayHeight - frameHeight) / 2;

    setFrame({
      w: frameWidth,
      h: frameHeight,
      left,
      top,
    });
  }, [aspectRatio, containerRef, videoRef]);

  useEffect(() => {
    recomputeFrame();
  }, [aspect, recomputeFrame]);

  useEffect(() => {
    const container = containerRef.current;
    const video = videoRef.current;

    if (!container || !video) return;

    const resizeObserver = new ResizeObserver(recomputeFrame);
    resizeObserver.observe(container);

    const handleVideoResize = () => recomputeFrame();
    const handleVideoLoaded = () => recomputeFrame();

    video.addEventListener("loadedmetadata", handleVideoLoaded);
    video.addEventListener("resize", handleVideoResize);

    const timeoutId = setTimeout(recomputeFrame, 300);

    return () => {
      clearTimeout(timeoutId);
      resizeObserver.disconnect();
      video.removeEventListener("loadedmetadata", handleVideoLoaded);
      video.removeEventListener("resize", handleVideoResize);
    };
  }, [containerRef, videoRef, recomputeFrame]);

  return { frame, recomputeFrame };
}
