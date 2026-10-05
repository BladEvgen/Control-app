import { Link } from "../RouterUtils";

export interface BreadcrumbItem {
  label: string;
  path?: string;
  onClick?: () => void;
}

export default function Breadcrumbs({
  items,
  className = "",
}: {
  items: BreadcrumbItem[];
  className?: string;
}) {
  if (items.length === 0) return null;
  return (
    <nav className={`detail-path ${className}`} aria-label="Путь">
      {items.map((item, index) => (
        <span key={`${item.label}-${index}`}>
          {index > 0 && <span aria-hidden>/ </span>}
          {item.path ? (
            <Link to={item.path}>{item.label}</Link>
          ) : item.onClick ? (
            <button type="button" onClick={item.onClick}>
              {item.label}
            </button>
          ) : (
            <span aria-current="page">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
