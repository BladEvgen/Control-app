import React from "react";
import ReactDOM from "react-dom/client";
import { Provider } from "react-redux";
import App from "./App.tsx";
import ErrorBoundary from "./components/ErrorBoundary.tsx";
import "./index.css";
import axios from "axios";
import { store } from "./store";
import { clearHardReloadParams } from "./utils/appAutoReload";
import {
  startAppVersionGuard,
  handleBuildSkewDetected,
  requestAppVersionCheck,
} from "./utils/appVersionGuard";
import { CURRENT_APP_BUILD_META } from "./utils/appBuild";
import { tryRecoverChunkLoadError } from "./utils/chunkRecovery";
import { isNavigationTransitionPending } from "./utils/pageLifecycle";

declare global {
  interface Window {
    __APP_BOOT__?: {
      markMounted?: () => void;
      showFallback?: (reason?: string, details?: string) => void;
      showReloading?: (message?: string) => void;
    };
    __APP_VERSION_GUARD__?: {
      currentBuild: typeof CURRENT_APP_BUILD_META;
      checkNow: (reason?: string) => Promise<void>;
    };
  }
}

axios.defaults.xsrfCookieName = "csrftoken";
axios.defaults.xsrfHeaderName = "X-CSRFToken";

window.__APP_VERSION_GUARD__ = {
  currentBuild: CURRENT_APP_BUILD_META,
  checkNow: (reason = "manual-debug") => requestAppVersionCheck(reason),
};

window.addEventListener("vite:preloadError", (event) => {
  if (isNavigationTransitionPending()) return;
  event.preventDefault();
  void handleBuildSkewDetected("vite:preloadError", event.payload);
});

window.addEventListener("unhandledrejection", (event) => {
  if (isNavigationTransitionPending()) return;
  if (tryRecoverChunkLoadError(event.reason)) {
    event.preventDefault();
  }
});

window.addEventListener("error", (event) => {
  if (isNavigationTransitionPending()) return;
  if (tryRecoverChunkLoadError(event.error ?? event.message)) {
    event.preventDefault();
  }
});

const markMountedSafely = () => {
  let marked = false;
  const mark = () => {
    if (marked) return;
    marked = true;
    clearHardReloadParams();
    window.__APP_BOOT__?.markMounted?.();
  };
  // Mark early to avoid bootstrap fallback racing with lazy route chunks.
  mark();
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(mark);
  });
  window.setTimeout(mark, 1200);
};

const rootEl = document.getElementById("root");
if (!rootEl) {
  document.body.innerHTML =
    "<p style='padding:2rem;text-align:center;font-family:system-ui'>Ошибка: элемент #root не найден.</p>";
  window.__APP_BOOT__?.showFallback?.("no-root");
} else {
  try {
    startAppVersionGuard();
    ReactDOM.createRoot(rootEl).render(
      <React.StrictMode>
        <ErrorBoundary>
          <Provider store={store}>
            <App />
          </Provider>
        </ErrorBoundary>
      </React.StrictMode>,
    );
    markMountedSafely();
  } catch (error) {
    console.error("React mount failed:", error);
    window.__APP_BOOT__?.showFallback?.(
      "react-mount",
      error instanceof Error ? error.message : String(error),
    );
  }
}
