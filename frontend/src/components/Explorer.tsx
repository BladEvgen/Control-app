import { useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import {
  FaChevronLeft,
  FaChevronRight,
  FaFolder,
  FaUsers,
} from "react-icons/fa";
import { Link } from "../RouterUtils";
import type { IBreadcrumbPathItem } from "../schemas/IData";
import { formatDepartmentName } from "../utils/utils";

const ease = [0.22, 1, 0.36, 1] as const;
const rowMotion = (index: number) => ({
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.28, ease, delay: Math.min(index, 14) * 0.02 },
});

export function DetailHead({
  path,
  title,
  meta,
  actions,
}: {
  path?: IBreadcrumbPathItem[];
  title: string;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  const ancestors = (path ?? []).slice(0, -1);
  return (
    <header className="detail-head">
      <div style={{ minWidth: 0 }}>
        {ancestors.length > 0 && (
          <nav className="detail-path" aria-label="Путь">
            {ancestors.map((item, index) => (
              <span key={item.id}>
                {index > 0 && <span aria-hidden>/ </span>}
                <Link to={`/department/${encodeURIComponent(item.id)}`}>
                  {formatDepartmentName(item.name)}
                </Link>
              </span>
            ))}
          </nav>
        )}
        <h1>{title}</h1>
        {meta && <p className="detail-meta">{meta}</p>}
      </div>
      {actions}
    </header>
  );
}

export function UnitRow({
  to,
  name,
  count,
  folder,
  index,
}: {
  to: string;
  name: string;
  count?: number;
  folder: boolean;
  index: number;
}) {
  return (
    <motion.li {...rowMotion(index)}>
      <Link to={to} className="row">
        <span className="row-icon">
          {folder ? <FaFolder aria-hidden /> : <FaUsers aria-hidden />}
        </span>
        <span className="row-body">
          <span className="row-title">{name}</span>
        </span>
        {count !== undefined && (
          <span className="row-count">{count.toLocaleString("ru-RU")}</span>
        )}
        <FaChevronRight className="row-go" aria-hidden />
      </Link>
    </motion.li>
  );
}

export function PersonRow({
  to,
  name,
  sub,
  photo,
  index,
}: {
  to: string;
  name: string;
  sub?: string;
  photo?: string | null;
  index: number;
}) {
  const [broken, setBroken] = useState(false);
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0] ?? "")
    .join("")
    .toUpperCase();
  return (
    <motion.li {...rowMotion(index)}>
      <Link to={to} className="row">
        {photo && !broken ? (
          <img
            className="row-photo"
            src={photo}
            alt=""
            loading="lazy"
            onError={() => setBroken(true)}
          />
        ) : (
          <span className="row-initials" aria-hidden>
            {initials}
          </span>
        )}
        <span className="row-body">
          <span className="row-title">{name}</span>
          {sub && <span className="row-sub">{sub}</span>}
        </span>
        <FaChevronRight className="row-go" aria-hidden />
      </Link>
    </motion.li>
  );
}

export function Pager({
  page,
  pageCount,
  onPage,
}: {
  page: number;
  pageCount: number;
  onPage: (page: number) => void;
}) {
  if (pageCount < 2) return null;
  return (
    <nav className="ws-pager" aria-label="Страницы">
      <button
        type="button"
        disabled={page === 0}
        onClick={() => onPage(page - 1)}
        aria-label="Назад"
      >
        <FaChevronLeft aria-hidden />
      </button>
      <span aria-live="polite">
        {page + 1} из {pageCount}
      </span>
      <button
        type="button"
        disabled={page + 1 === pageCount}
        onClick={() => onPage(page + 1)}
        aria-label="Вперёд"
      >
        <FaChevronRight aria-hidden />
      </button>
    </nav>
  );
}
