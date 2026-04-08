import {
  proactiveRefreshIfNeeded,
  scheduleNextRefreshBeforeExpiry,
} from "../api.ts";

const TOKEN_POLL_FALLBACK_INTERVAL_MS = 5 * 60 * 1000;

export function installAuthWakeRefreshListeners(): () => void {
  let pollId: number | null = null;

  const clearPoll = () => {
    if (pollId !== null) {
      window.clearInterval(pollId);
      pollId = null;
    }
  };

  const startPoll = () => {
    clearPoll();
    pollId = window.setInterval(() => {
      void proactiveRefreshIfNeeded();
    }, TOKEN_POLL_FALLBACK_INTERVAL_MS);
  };

  const onVisibility = () => {
    void proactiveRefreshIfNeeded();
    scheduleNextRefreshBeforeExpiry();
  };

  const onFocus = () => {
    void proactiveRefreshIfNeeded();
    scheduleNextRefreshBeforeExpiry();
  };

  const onPageShow = () => {
    void proactiveRefreshIfNeeded();
    scheduleNextRefreshBeforeExpiry();
  };

  document.addEventListener("visibilitychange", onVisibility);
  window.addEventListener("focus", onFocus);
  window.addEventListener("pageshow", onPageShow);

  void proactiveRefreshIfNeeded();
  scheduleNextRefreshBeforeExpiry();
  startPoll();

  return () => {
    document.removeEventListener("visibilitychange", onVisibility);
    window.removeEventListener("focus", onFocus);
    window.removeEventListener("pageshow", onPageShow);
    clearPoll();
  };
}
