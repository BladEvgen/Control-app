import { useEffect } from "react";
import axiosInstance, { getCookie } from "../api";

const BEAT_MS = 5 * 60 * 1000;
const INPUT_EVENTS = ["pointerdown", "keydown", "wheel", "touchstart"] as const;

export function useActivityHeartbeat(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;
    let lastInput = 0;
    const markInput = (): void => {
      lastInput = Date.now();
    };
    INPUT_EVENTS.forEach((name) =>
      window.addEventListener(name, markInput, { passive: true }),
    );
    const id = window.setInterval(() => {
      const recentInput = Date.now() - lastInput < BEAT_MS;
      if (
        !recentInput ||
        document.visibilityState !== "visible" ||
        !getCookie("access_token")
      )
        return;
      void axiosInstance.post("activity/heartbeat/").catch(() => undefined);
    }, BEAT_MS);
    return () => {
      window.clearInterval(id);
      INPUT_EVENTS.forEach((name) =>
        window.removeEventListener(name, markInput),
      );
    };
  }, [enabled]);
}
