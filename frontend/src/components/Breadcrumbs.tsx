import { memo, useMemo } from "react";
import { Link, useNavigate } from "../RouterUtils";
import { FaHome, FaChevronRight, FaBuilding } from "react-icons/fa";
import { motion } from "framer-motion";

export interface BreadcrumbItem {
  label: string;
  path?: string;
  onClick?: () => void;
}

interface BreadcrumbsProps {
  items: BreadcrumbItem[];
  className?: string;
}

const Breadcrumbs: React.FC<BreadcrumbsProps> = memo(({ items, className = "" }) => {
  const navigate = useNavigate();

  const handleClick = useMemo(
    () => (item: BreadcrumbItem) => {
      if (item.onClick) {
        item.onClick();
      } else if (item.path) {
        navigate(item.path);
      }
    },
    [navigate]
  );

  if (items.length === 0) {
    return null;
  }

  return (
    <div className={`flex flex-col md:flex-row md:items-center md:justify-between gap-3 ${className}`}>
      <nav
        className="flex items-center py-1 -mx-1 md:mx-0"
        aria-label="Breadcrumb"
      >
        <ol className="flex flex-wrap items-center gap-y-1 gap-x-1 md:gap-x-2 min-w-0">
          {/* Главная страница */}
          <li className="flex-shrink-0">
            <Link
              to="/"
              className="flex items-center text-gray-500 hover:text-primary-600 dark:text-gray-400 dark:hover:text-primary-400 transition-colors duration-200 p-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800"
              aria-label="Главная страница"
            >
              <FaHome className="w-4 h-4 md:w-5 md:h-5" />
            </Link>
          </li>

          {items.map((item, index) => {
            const isLast = index === items.length - 1;
            const isClickable = !isLast && (item.path || item.onClick);

            return (
              <li key={index} className="flex items-center">
                <FaChevronRight className="w-3 h-3 md:w-4 md:h-4 text-gray-400 dark:text-gray-500 mx-0.5 md:mx-1 flex-shrink-0" />
                {isClickable ? (
                  <motion.button
                    onClick={() => handleClick(item)}
                    className="flex items-center text-gray-600 hover:text-primary-600 dark:text-gray-300 dark:hover:text-primary-400 transition-colors duration-200 font-medium px-1 py-0.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 min-w-0"
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    title={item.label}
                  >
                    {index === 0 && (
                      <FaBuilding className="w-3 h-3 md:w-4 md:h-4 mr-1 md:mr-2 flex-shrink-0" />
                    )}
                    <span className="truncate max-w-[120px] sm:max-w-[180px] md:max-w-[280px]">{item.label}</span>
                  </motion.button>
                ) : (
                  <span
                    className="flex items-center text-gray-900 dark:text-gray-100 font-semibold px-1 min-w-0"
                    aria-current="page"
                    title={item.label}
                  >
                    {index === 0 && (
                      <FaBuilding className="w-3 h-3 md:w-4 md:h-4 mr-1 md:mr-2 flex-shrink-0" />
                    )}
                    <span className="truncate max-w-[120px] sm:max-w-[180px] md:max-w-[280px]">{item.label}</span>
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </nav>
    </div>
  );
});

Breadcrumbs.displayName = "Breadcrumbs";

export default Breadcrumbs;

