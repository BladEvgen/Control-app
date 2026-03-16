import React from "react";
import ReactDOM from "react-dom/client";
import { Provider } from "react-redux";
import App from "./App.tsx";
import ErrorBoundary from "./components/ErrorBoundary.tsx";
import "./index.css";
import axios from "axios";
import { store } from "./store";
import { tryRecoverChunkLoadError } from "./utils/chunkRecovery";

declare global {
  interface Window {
    __APP_BOOT__?: {
      markMounted?: () => void;
      showFallback?: (reason?: string, details?: string) => void;
    };
  }
}

axios.defaults.xsrfCookieName = "csrftoken";
axios.defaults.xsrfHeaderName = "X-CSRFToken";

const clearHardReloadParam = () => {
  try {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("__hard_reload")) return;
    url.searchParams.delete("__hard_reload");
    const next =
      `${url.pathname}${url.search ? url.search : ""}${url.hash ? url.hash : ""}` ||
      "/";
    window.history.replaceState(window.history.state, "", next);
  } catch {
    // ignore URL/history issues
  }
};

let isPageUnloading = false;
window.addEventListener("beforeunload", () => {
  isPageUnloading = true;
});
window.addEventListener("pagehide", () => {
  isPageUnloading = true;
});

window.addEventListener("unhandledrejection", (event) => {
  if (isPageUnloading) return;
  if (tryRecoverChunkLoadError(event.reason)) {
    event.preventDefault();
  }
});

window.addEventListener("error", (event) => {
  if (isPageUnloading) return;
  if (tryRecoverChunkLoadError(event.error ?? event.message)) {
    event.preventDefault();
  }
});

const markMountedSafely = () => {
  let marked = false;
  const mark = () => {
    if (marked) return;
    marked = true;
    clearHardReloadParam();
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
