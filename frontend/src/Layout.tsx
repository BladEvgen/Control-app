import React, {
  useEffect,
  useState,
  ReactNode,
  useRef,
  useCallback,
  useMemo,
} from "react";
import { useLocation } from "react-router-dom";
import HeaderComponent from "./components/HeaderComponent";
import FooterComponent from "./components/FooterComponent";
import AuthWebSocketInitializer from "./components/AuthWebSocketInitializer";
import ScrollToTopButton from "./components/ScrollToTopButton";
import AttendanceExcelDownloadBanner from "./components/AttendanceExcelDownloadBanner";
import { AuthSessionWakeBridge } from "./authSession/AuthSessionWakeBridge.tsx";

interface LayoutProps {
  children: ReactNode;
}

const safeGetItem = (key: string, defaultValue: string): string => {
  try {
    const value = localStorage.getItem(key);
    return value !== null ? value : defaultValue;
  } catch (error) {
    console.error("Error accessing localStorage:", error);
    return defaultValue;
  }
};

const safeSetItem = (key: string, value: string): void => {
  try {
    localStorage.setItem(key, value);
  } catch (error) {
    console.error("Error setting localStorage:", error);
  }
};

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const location = useLocation();
  const normalizedPath = useMemo(
    () => location.pathname.toLowerCase(),
    [location.pathname],
  );
  const isLoginRoute = /\/login\/?$/.test(location.pathname);
  const hasKioskFlag =
    new URLSearchParams(location.search).get("kiosk") === "1";
  const isKioskCompatiblePath =
    /\/(photo|map|dashboard)\/?$/.test(normalizedPath) ||
    /\/childdepartment\/[^/]+\/?$/.test(normalizedPath);
  const isKioskRoute = hasKioskFlag && isKioskCompatiblePath;

  const [theme, setTheme] = useState<string>(() => {
    return safeGetItem("theme", "light");
  });

  const [isChangingTheme, setIsChangingTheme] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const contentCache = useRef<ReactNode>(children);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    safeSetItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    if (!isChangingTheme) {
      contentCache.current = children;
    }
  }, [children, isChangingTheme]);

  const toggleTheme = useCallback(() => {
    setIsChangingTheme(true);
    contentCache.current = children;

    const reduceMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduceMotion) {
      document.documentElement.classList.add("theme-transition-active");
    }

    setTimeout(() => {
      setTheme(theme === "dark" ? "light" : "dark");
      setTimeout(() => {
        setIsChangingTheme(false);
        document.documentElement.classList.remove("theme-transition-active");
      }, reduceMotion ? 0 : 440);
    }, 50);
  }, [theme, children]);

  return (
    <div className="flex flex-col min-h-screen overflow-hidden">
      <AuthSessionWakeBridge />
      {!isLoginRoute && <AuthWebSocketInitializer />}

      <div
        className="fixed inset-0 z-[-1] min-h-[100dvh] w-full overflow-hidden transition-colors duration-1000"
        aria-hidden
      >
        <div
          className={`absolute inset-0 transition-colors duration-1000 ${
            theme === "dark"
              ? "bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950"
              : "bg-gradient-to-br from-slate-100 via-indigo-50/95 to-violet-100/90"
          }`}
        />
        <div className="layout-living-mesh" />
        <div
          className={`pointer-events-none absolute -left-[12%] -top-[18%] h-[min(85vw,720px)] w-[min(85vw,720px)] rounded-full blur-3xl motion-safe:animate-layout-orb-a motion-reduce:animate-none ${
            theme === "dark"
              ? "bg-primary-600/25"
              : "bg-primary-400/42"
          }`}
        />
        <div
          className={`pointer-events-none absolute -bottom-[14%] -right-[8%] h-[min(78vw,640px)] w-[min(78vw,640px)] rounded-full blur-3xl motion-safe:animate-layout-orb-b motion-reduce:animate-none ${
            theme === "dark"
              ? "bg-secondary-600/22"
              : "bg-secondary-400/38"
          }`}
        />
        <div
          className={`pointer-events-none absolute left-1/2 top-1/2 h-[min(110vw,900px)] w-[min(110vw,900px)] -translate-x-1/2 -translate-y-1/2 rounded-full blur-3xl motion-safe:animate-layout-ambient motion-reduce:animate-none ${
            theme === "dark"
              ? "bg-indigo-500/12"
              : "bg-indigo-400/28"
          }`}
        />
        {theme !== "dark" ? (
          <div className="pointer-events-none absolute bottom-[6%] left-[-5%] h-[min(52vw,400px)] w-[min(52vw,400px)] rounded-full bg-teal-200/40 blur-3xl" />
        ) : null}
        <div
          className={`pointer-events-none absolute inset-0 bg-gradient-to-t transition-opacity duration-1000 ${
            theme === "dark"
              ? "from-slate-950/40 via-transparent to-slate-950/30"
              : "from-white/12 via-transparent to-violet-100/35"
          }`}
        />
      </div>

      {!isKioskRoute && !isLoginRoute && (
        <HeaderComponent toggleTheme={toggleTheme} currentTheme={theme} />
      )}
      {!isKioskRoute && !isLoginRoute && <AttendanceExcelDownloadBanner />}

      <main
        className={`flex-1 relative ${
          isKioskRoute
            ? "p-0 min-h-[100dvh] overflow-hidden"
            : isLoginRoute
              ? "pt-0 pb-0"
              : "pt-6 pb-24 lg:pb-10"
        }`}
      >
        <div
          ref={contentRef}
          className={`relative z-10 transition-opacity duration-300 ${
            isKioskRoute
              ? "w-full h-full max-w-none p-0"
              : isLoginRoute
                ? "w-full max-w-none px-0"
                : "container mx-auto px-4"
          }`}
          style={{ opacity: isChangingTheme ? 0.6 : 1 }}
        >
          {isChangingTheme && contentCache.current
            ? contentCache.current
            : children}
        </div>
      </main>

      {!isKioskRoute && !isLoginRoute && <FooterComponent />}
      {!isLoginRoute && !isKioskRoute && <ScrollToTopButton />}
    </div>
  );
};

export default Layout;
