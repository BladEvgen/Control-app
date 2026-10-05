import { useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import Sidebar, { Brand, MobileDock } from "./components/Sidebar";
import StructureTree from "./components/StructureTree";
import ShellFooter from "./components/ShellFooter";
import AuthWebSocketInitializer from "./components/AuthWebSocketInitializer";
import AttendanceExcelDownloadBanner from "./components/AttendanceExcelDownloadBanner";
import { AuthSessionWakeBridge } from "./authSession/AuthSessionWakeBridge";

const readTheme = (): string => {
  try {
    return localStorage.getItem("theme") ?? "light";
  } catch {
    return "light";
  }
};

export default function Layout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const reducedMotion = useReducedMotion();
  const path = location.pathname.toLowerCase();
  const isLoginRoute = /\/login\/?$/.test(path);
  const isKioskRoute =
    new URLSearchParams(location.search).get("kiosk") === "1" &&
    (/\/(photo|map|dashboard)\/?$/.test(path) ||
      /\/childdepartment\/[^/]+\/?$/.test(path));
  const isStructure = /\/app\/?$|\/(department|childdepartment)\//.test(path);
  const [theme, setTheme] = useState(readTheme);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* Theme works without storage. */
    }
  }, [theme]);

  const toggleTheme = (): void => {
    const root = document.documentElement;
    if (!reducedMotion) root.classList.add("theme-transition-active");
    setTheme((current) => (current === "dark" ? "light" : "dark"));
    window.setTimeout(
      () => root.classList.remove("theme-transition-active"),
      450,
    );
  };

  const page = (
    <motion.div
      key={location.pathname}
      initial={reducedMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className={isStructure ? "detail" : undefined}
    >
      {children}
    </motion.div>
  );

  if (isLoginRoute || isKioskRoute) {
    return (
      <div className="workspace">
        <AuthSessionWakeBridge />
        {!isLoginRoute && <AuthWebSocketInitializer />}
        <main
          className={
            isKioskRoute ? "workspace-kiosk-content" : "workspace-login"
          }
        >
          {children}
        </main>
      </div>
    );
  }

  return (
    <div className="workspace shell">
      <div className="shell-crest shell-crest-page" aria-hidden />
      <AuthSessionWakeBridge />
      <AuthWebSocketInitializer />
      <a href="#main-content" className="workspace-skip-link">
        К содержимому
      </a>
      <aside className="shell-rail">
        <Sidebar theme={theme} toggleTheme={toggleTheme} />
      </aside>
      <div className="shell-canvas">
        <div className="shell-crests" aria-hidden>
          <div className="shell-crest shell-crest-canvas" />
        </div>
        <div className="shell-mobilebar">
          <Brand />
        </div>
        <main id="main-content" tabIndex={-1} className="shell-main">
          {isStructure ? (
            <div className="explorer">
              <StructureTree />
              {page}
            </div>
          ) : (
            page
          )}
        </main>
        <ShellFooter />
      </div>
      <MobileDock theme={theme} toggleTheme={toggleTheme} />
      <AttendanceExcelDownloadBanner />
    </div>
  );
}
