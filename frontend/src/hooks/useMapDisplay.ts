import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useMuiDarkSync } from "../faceLab/useMuiDarkSync";

type FullscreenDocument = Document & {
  webkitFullscreenElement?: Element;
  webkitExitFullscreen?: () => Promise<void>;
};
type FullscreenElement = HTMLElement & {
  webkitRequestFullscreen?: () => Promise<void>;
};

export function useMapDisplay() {
  const location = useLocation();
  const navigate = useNavigate();
  const kiosk = new URLSearchParams(location.search).get("kiosk") === "1";
  const dark = useMuiDarkSync();
  const [fullscreenBusy, setFullscreenBusy] = useState(false);
  const [displayError, setDisplayError] = useState<string | null>(null);
  const setKiosk = useCallback(
    (value: boolean) => {
      const params = new URLSearchParams(location.search);
      if (value) params.set("kiosk", "1");
      else params.delete("kiosk");
      navigate(
        { pathname: location.pathname, search: params.toString() },
        { replace: true },
      );
    },
    [location.pathname, location.search, navigate],
  );

  useEffect(() => {
    const sync = (): void => {
      const doc = document as FullscreenDocument;
      setKiosk(Boolean(doc.fullscreenElement ?? doc.webkitFullscreenElement));
    };
    document.addEventListener("fullscreenchange", sync);
    document.addEventListener("webkitfullscreenchange", sync);
    return () => {
      document.removeEventListener("fullscreenchange", sync);
      document.removeEventListener("webkitfullscreenchange", sync);
    };
  }, [setKiosk]);

  const toggleFullscreen = useCallback(async () => {
    if (fullscreenBusy) return;
    setFullscreenBusy(true);
    setDisplayError(null);
    const doc = document as FullscreenDocument;
    const root = document.documentElement as FullscreenElement;
    try {
      if (doc.fullscreenElement ?? doc.webkitFullscreenElement) {
        const exit = doc.exitFullscreen ?? doc.webkitExitFullscreen;
        await exit?.call(doc);
        setKiosk(false);
      } else if (kiosk) {
        setKiosk(false);
      } else {
        const enter = root.requestFullscreen ?? root.webkitRequestFullscreen;
        await enter?.call(root);
        setKiosk(true);
      }
    } catch {
      setDisplayError("Не удалось переключить полноэкранный режим.");
    } finally {
      setFullscreenBusy(false);
    }
  }, [fullscreenBusy, kiosk, setKiosk]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "F11") {
        event.preventDefault();
        void toggleFullscreen();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [toggleFullscreen]);
  return { dark, kiosk, fullscreenBusy, toggleFullscreen, displayError };
}
