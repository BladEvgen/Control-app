const RELOAD_SHORTCUT_GRACE_MS = 1500;

const isBrowser = typeof window !== "undefined";

let navigationTransitionInFlight = false;
let lastReloadShortcutAt = 0;

const isReloadShortcutEvent = (event: KeyboardEvent): boolean => {
  const key = event.key.toLowerCase();
  if (key === "f5") {
    return true;
  }
  return key === "r" && (event.ctrlKey || event.metaKey);
};

if (isBrowser) {
  window.addEventListener(
    "beforeunload",
    () => {
      navigationTransitionInFlight = true;
    },
    { capture: true },
  );

  window.addEventListener(
    "pagehide",
    () => {
      navigationTransitionInFlight = true;
    },
    { capture: true },
  );

  window.addEventListener(
    "keydown",
    (event) => {
      if (!isReloadShortcutEvent(event)) return;
      lastReloadShortcutAt = Date.now();
    },
    { capture: true },
  );
}

export const hasRecentReloadShortcut = (): boolean => {
  if (!isBrowser) return false;
  return Date.now() - lastReloadShortcutAt < RELOAD_SHORTCUT_GRACE_MS;
};

export const isNavigationTransitionPending = (): boolean => {
  return navigationTransitionInFlight || hasRecentReloadShortcut();
};
