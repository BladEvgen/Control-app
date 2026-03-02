import { useEffect, useState } from "react";

type WindowSize = {
  width: number;
  height: number;
  orientation: "portrait" | "landscape";
  aspectRatio: number;
  aspectBucket:
    | "portrait-tall"
    | "portrait-classic"
    | "square-ish"
    | "landscape-classic"
    | "landscape-wide"
    | "landscape-ultrawide";
  resolutionTier: "sd" | "hd" | "fhd" | "qhd" | "uhd";
};

const getAspectBucket = (aspectRatio: number): WindowSize["aspectBucket"] => {
  if (aspectRatio <= 0.68) return "portrait-tall";
  if (aspectRatio < 0.9) return "portrait-classic";
  if (aspectRatio <= 1.2) return "square-ish";
  if (aspectRatio <= 1.78) return "landscape-classic";
  if (aspectRatio <= 2.1) return "landscape-wide";
  return "landscape-ultrawide";
};

const getResolutionTier = (
  width: number,
  height: number,
): WindowSize["resolutionTier"] => {
  const longSide = Math.max(width, height);
  if (longSide >= 3840) return "uhd";
  if (longSide >= 2560) return "qhd";
  if (longSide >= 1920) return "fhd";
  if (longSide >= 1280) return "hd";
  return "sd";
};

const getViewportSize = (): WindowSize => {
  const vv = window.visualViewport;
  const width = Math.max(
    1,
    Math.round(
      vv?.width ??
        window.innerWidth ??
        document.documentElement.clientWidth ??
        1,
    ),
  );
  const height = Math.max(
    1,
    Math.round(
      vv?.height ??
        window.innerHeight ??
        document.documentElement.clientHeight ??
        1,
    ),
  );
  const orientation = width >= height ? "landscape" : "portrait";
  const aspectRatio = width / height;
  return {
    width,
    height,
    orientation,
    aspectRatio,
    aspectBucket: getAspectBucket(aspectRatio),
    resolutionTier: getResolutionTier(width, height),
  };
};

const useWindowSize = () => {
  const [windowSize, setWindowSize] = useState<WindowSize>(getViewportSize);

  useEffect(() => {
    let rafId: number | null = null;
    let settleTimeouts: number[] = [];

    const applySize = () => {
      setWindowSize((prev) => {
        const next = getViewportSize();
        if (prev.width === next.width && prev.height === next.height) {
          return prev;
        }
        return next;
      });
    };

    const scheduleApply = () => {
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId);
      }
      rafId = window.requestAnimationFrame(() => {
        rafId = null;
        applySize();
      });
    };

    const runSettledUpdate = () => {
      scheduleApply();
      settleTimeouts.forEach((id) => window.clearTimeout(id));
      settleTimeouts = [80, 180, 320, 520].map((delay) =>
        window.setTimeout(scheduleApply, delay),
      );
    };

    window.addEventListener("resize", runSettledUpdate);
    window.addEventListener("orientationchange", runSettledUpdate);
    document.addEventListener("fullscreenchange", runSettledUpdate);
    document.addEventListener("webkitfullscreenchange", runSettledUpdate);
    document.addEventListener("mozfullscreenchange", runSettledUpdate);
    document.addEventListener("MSFullscreenChange", runSettledUpdate);
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", runSettledUpdate);
      window.visualViewport.addEventListener("scroll", runSettledUpdate);
    }

    runSettledUpdate();

    return () => {
      window.removeEventListener("resize", runSettledUpdate);
      window.removeEventListener("orientationchange", runSettledUpdate);
      document.removeEventListener("fullscreenchange", runSettledUpdate);
      document.removeEventListener("webkitfullscreenchange", runSettledUpdate);
      document.removeEventListener("mozfullscreenchange", runSettledUpdate);
      document.removeEventListener("MSFullscreenChange", runSettledUpdate);
      if (window.visualViewport) {
        window.visualViewport.removeEventListener("resize", runSettledUpdate);
        window.visualViewport.removeEventListener("scroll", runSettledUpdate);
      }
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId);
      }
      settleTimeouts.forEach((id) => window.clearTimeout(id));
    };
  }, []);

  return windowSize;
};

export default useWindowSize;
