import type { MouseEvent } from "react";
import { useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  FaChartPie,
  FaChevronDown,
  FaImages,
  FaMapMarkedAlt,
  FaMoon,
  FaSignOutAlt,
  FaSitemap,
  FaSun,
  FaUpload,
} from "react-icons/fa";
import Dropdown from "./Dropdown";
import logoSrc from "../assets/logo.png";
import { Link, useNavigate } from "../RouterUtils";
import { useAuth } from "../store/hooks";
import { apiUrl } from "../../apiConfig";

const sections = [
  { to: "/", label: "Структура", icon: FaSitemap },
  { to: "/dashboard", label: "Аналитика", icon: FaChartPie },
  { to: "/map", label: "Карта", icon: FaMapMarkedAlt },
  { to: "/photo", label: "Фото", icon: FaImages },
];
const spring = { type: "spring", stiffness: 420, damping: 38 } as const;

type ShellNavProps = { theme: string; toggleTheme: () => void };

function useShellNav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const isActive = (path: string): boolean =>
    path === "/"
      ? /\/app\/?$|\/department\/|\/childDepartment\/|\/staffDetail\//i.test(
          pathname,
        )
      : pathname.startsWith(`/app${path}`);
  const signOut = (): void => {
    logout();
    navigate("/login");
  };
  return { username: user?.username ?? "", pathname, isActive, signOut };
}

function ThemeIcon({ theme }: { theme: string }) {
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.span
        key={theme}
        style={{ display: "grid" }}
        initial={{ rotate: -90, opacity: 0, scale: 0.6 }}
        animate={{ rotate: 0, opacity: 1, scale: 1 }}
        exit={{ rotate: 90, opacity: 0, scale: 0.6 }}
        transition={{ duration: 0.22 }}
      >
        {theme === "dark" ? <FaSun aria-hidden /> : <FaMoon aria-hidden />}
      </motion.span>
    </AnimatePresence>
  );
}

export function Brand() {
  return (
    <Link to="/" className="rail-brand">
      <img src={logoSrc} alt="" className="rail-brand-logo" />
      Посещаемость
    </Link>
  );
}

export default function Sidebar({ theme, toggleTheme }: ShellNavProps) {
  const { username, pathname, isActive, signOut } = useShellNav();
  return (
    <>
      <Brand />
      <nav className="rail-nav" aria-label="Разделы">
        {sections.map(({ to, label, icon: Icon }) => {
          const active = isActive(to);
          return (
            <Link
              key={to}
              to={to}
              className="rail-link"
              aria-current={active ? "page" : undefined}
            >
              {active && (
                <motion.span
                  layoutId="rail-pill"
                  className="rail-pill"
                  transition={spring}
                />
              )}
              <Icon aria-hidden />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="rail-bottom">
        <button type="button" className="rail-theme" onClick={toggleTheme}>
          <ThemeIcon theme={theme} />
          {theme === "dark" ? "Светлая тема" : "Тёмная тема"}
        </button>
        <Dropdown
          side="top"
          closeKey={pathname}
          trigger={({ toggle, ...aria }) => (
            <button
              type="button"
              className="rail-account"
              onClick={toggle}
              {...aria}
            >
              <span className="ws-avatar" aria-hidden>
                {username.slice(0, 1).toUpperCase() || "?"}
              </span>
              <span className="rail-account-name">{username || "Аккаунт"}</span>
              <FaChevronDown className="ws-chevron" aria-hidden />
            </button>
          )}
        >
          {(close) => (
            <>
              <a className="ws-menu-item" href={`${apiUrl}/upload/`}>
                <FaUpload aria-hidden />
                Импорт данных
              </a>
              <div className="ws-menu-sep" />
              <button
                type="button"
                className="ws-menu-item"
                onClick={() => {
                  close();
                  signOut();
                }}
              >
                <FaSignOutAlt aria-hidden />
                Выйти
              </button>
            </>
          )}
        </Dropdown>
      </div>
    </>
  );
}

export function MobileDock({ theme, toggleTheme }: ShellNavProps) {
  const { username, pathname, isActive, signOut } = useShellNav();
  return (
    <nav className="dock" aria-label="Разделы">
      {sections.map(({ to, label, icon: Icon }) => {
        const active = isActive(to);
        return (
          <Link
            key={to}
            to={to}
            className="dock-item"
            aria-current={active ? "page" : undefined}
            onClick={(event: MouseEvent) => {
              if (
                to !== "/" ||
                !/\/app\/?$|\/(department|childDepartment)\//i.test(pathname)
              )
                return;
              event.preventDefault();
              window.dispatchEvent(new Event("structure-sheet"));
            }}
          >
            {active && (
              <motion.span
                layoutId="dock-pill"
                className="dock-pill"
                transition={spring}
              />
            )}
            <Icon aria-hidden />
            <span>{label}</span>
          </Link>
        );
      })}
      <Dropdown
        side="top"
        align="end"
        closeKey={pathname}
        panelClassName="dock-menu"
        trigger={({ toggle, ...aria }) => (
          <button
            type="button"
            className="dock-item"
            onClick={toggle}
            {...aria}
          >
            <span className="ws-avatar dock-avatar" aria-hidden>
              {username.slice(0, 1).toUpperCase() || "?"}
            </span>
            <span>Профиль</span>
          </button>
        )}
      >
        {(close) => (
          <>
            <p className="dock-menu-user">{username || "Аккаунт"}</p>
            <button
              type="button"
              className="ws-menu-item"
              onClick={toggleTheme}
            >
              <ThemeIcon theme={theme} />
              {theme === "dark" ? "Светлая тема" : "Тёмная тема"}
            </button>
            <a className="ws-menu-item" href={`${apiUrl}/upload/`}>
              <FaUpload aria-hidden />
              Импорт данных
            </a>
            <div className="ws-menu-sep" />
            <button
              type="button"
              className="ws-menu-item"
              onClick={() => {
                close();
                signOut();
              }}
            >
              <FaSignOutAlt aria-hidden />
              Выйти
            </button>
          </>
        )}
      </Dropdown>
    </nav>
  );
}
