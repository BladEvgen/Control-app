import { FaGithub } from "react-icons/fa";
import logoSrc from "../assets/logo.png";
import { CURRENT_APP_BUILD_META } from "../utils/appBuild";

const builtAt = new Date(
  CURRENT_APP_BUILD_META.buildEpochMs,
).toLocaleDateString("ru-RU", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

export default function ShellFooter() {
  return (
    <footer className="shell-footer">
      <span className="shell-footer-brand">
        <img src={logoSrc} alt="" />© {new Date().getFullYear()} КРМУ · Учёт
        посещаемости
      </span>
      <span className="shell-footer-meta">
        <span title={CURRENT_APP_BUILD_META.buildId}>Обновлено {builtAt}</span>
        <a
          href="https://github.com/bladEvgen"
          target="_blank"
          rel="noopener noreferrer"
        >
          <FaGithub aria-hidden />
          bladEvgen
        </a>
      </span>
    </footer>
  );
}
