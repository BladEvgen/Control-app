import { FaGithub } from "react-icons/fa";
import logoSrc from "../assets/logo.png";
import { CURRENT_APP_BUILD_META } from "../utils/appBuild";
import { localDate, REPORT_TIME_ZONE } from "../utils/reportDates";

const builtAt = new Date(
  CURRENT_APP_BUILD_META.buildEpochMs,
).toLocaleDateString("ru-RU", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: REPORT_TIME_ZONE,
});

export default function ShellFooter() {
  return (
    <footer className="shell-footer">
      <span className="shell-footer-brand">
        <img src={logoSrc} alt="" />© {localDate().slice(0, 4)} КРМУ · Учёт
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
