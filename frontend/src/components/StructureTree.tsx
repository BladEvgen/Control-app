import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { FaChevronRight, FaTimes } from "react-icons/fa";
import SearchField from "./SearchField";
import { Link } from "../RouterUtils";
import { useNavigationNodes } from "../hooks/useNavigationNodes";
import {
  activeDepartmentId,
  filterNavigation,
  navigationPath,
} from "../utils/departmentNavigation";
import { formatDepartmentName } from "../utils/utils";

const ease = [0.22, 1, 0.36, 1] as const;
const TREE_WIDTH_KEY = "control:tree-width";
const clampWidth = (width: number): number =>
  Math.min(440, Math.max(240, width));

function setTreeWidth(pane: HTMLElement | null, width: number): void {
  pane
    ?.closest<HTMLElement>(".explorer")
    ?.style.setProperty("--tree-w", `${width}px`);
}

export default function StructureTree() {
  const { pathname } = useLocation();
  const { nodes, status, retry } = useNavigationNodes();
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [sheetOpen, setSheetOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const paneRef = useRef<HTMLElement>(null);
  useEffect(() => {
    try {
      const saved = Number(localStorage.getItem(TREE_WIDTH_KEY));
      if (saved) setTreeWidth(paneRef.current, clampWidth(saved));
    } catch {
      /* Default width without storage. */
    }
  }, []);
  const startResize = (event: ReactPointerEvent<HTMLDivElement>): void => {
    const pane = paneRef.current;
    if (!pane) return;
    const startX = event.clientX;
    const startWidth = pane.getBoundingClientRect().width;
    let width = startWidth;
    const move = (e: PointerEvent): void => {
      width = clampWidth(startWidth + e.clientX - startX);
      setTreeWidth(pane, width);
    };
    const stop = (): void => {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", stop);
      document.body.classList.remove("is-resizing");
      try {
        localStorage.setItem(TREE_WIDTH_KEY, String(Math.round(width)));
      } catch {
        /* Width stays for this visit. */
      }
    };
    document.body.classList.add("is-resizing");
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", stop);
  };
  const roots = nodes.filter((node) => node.parent_id === null);
  const isRoot = /\/app\/?$/.test(pathname);
  const selected =
    nodes.find((node) => node.id === activeDepartmentId(pathname)) ??
    (isRoot && roots.length === 1 ? roots[0] : undefined);
  const selectedId = selected?.id;

  useEffect(() => setSheetOpen(false), [pathname]);
  useEffect(() => {
    const toggleSheet = (): void => setSheetOpen((value) => !value);
    window.addEventListener("structure-sheet", toggleSheet);
    return () => window.removeEventListener("structure-sheet", toggleSheet);
  }, []);
  useEffect(() => {
    if (!selected) return;
    setExpanded(
      (current) => new Set([...current, ...selected.ancestor_ids, selected.id]),
    );
    const timer = window.setTimeout(() => {
      scrollRef.current
        ?.querySelector('[aria-current="page"]')
        ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }, 320);
    return () => window.clearTimeout(timer);
  }, [selected]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      const target = event.target as HTMLElement;
      if (
        event.key !== "/" ||
        target.closest("input, textarea, [contenteditable]")
      )
        return;
      event.preventDefault();
      setSheetOpen(true);
      inputRef.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const searching = query.trim().length > 0;
  const visible = useMemo(
    () =>
      filterNavigation(nodes, query, expanded).slice(
        0,
        searching ? 150 : undefined,
      ),
    [nodes, query, expanded, searching],
  );
  const toggle = (id: string): void =>
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <>
      <div
        className="tree-scrim"
        data-open={sheetOpen}
        onClick={() => setSheetOpen(false)}
        aria-hidden
      />
      <aside
        ref={paneRef}
        className="tree-pane"
        data-open={sheetOpen}
        aria-label="Структура университета"
      >
        <div className="tree-sheet-head">
          <span>
            {selected ? formatDepartmentName(selected.name) : "Структура"}
          </span>
          <button
            type="button"
            className="ws-icon-button"
            onClick={() => setSheetOpen(false)}
            aria-label="Закрыть"
          >
            <FaTimes aria-hidden />
          </button>
        </div>
        <div className="tree-collapsible">
          <SearchField
            ref={inputRef}
            value={query}
            onChange={setQuery}
            placeholder="Найти отдел или группу"
            hint="/"
          />
          <div className="tree-scroll" ref={scrollRef}>
            {status === "loading" ? (
              <p className="tree-message">Загружаем структуру…</p>
            ) : status === "error" ? (
              <p className="tree-message">
                Структура не загрузилась.{" "}
                <button
                  type="button"
                  className="ws-link-button"
                  onClick={retry}
                >
                  Повторить
                </button>
              </p>
            ) : visible.length === 0 ? (
              <p className="tree-message">Ничего не найдено</p>
            ) : (
              <ul>
                <AnimatePresence initial={false}>
                  {visible.map((node) => {
                    const isSelected = node.id === selectedId;
                    return (
                      <motion.li
                        key={node.id}
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.22, ease }}
                        style={{ overflow: "hidden" }}
                      >
                        <div
                          className="tree-row"
                          onClick={(event) => {
                            if (
                              event.target === event.currentTarget &&
                              node.has_children
                            )
                              toggle(node.id);
                          }}
                          style={{
                            paddingLeft: searching
                              ? 0
                              : Math.min(node.ancestor_ids.length, 6) * 14,
                          }}
                        >
                          {isSelected && (
                            <motion.span
                              layoutId="tree-selected"
                              className="tree-selected"
                              transition={{
                                type: "spring",
                                stiffness: 500,
                                damping: 40,
                              }}
                            />
                          )}
                          {!searching && node.has_children ? (
                            <button
                              type="button"
                              className="tree-toggle"
                              onClick={() => toggle(node.id)}
                              aria-expanded={expanded.has(node.id)}
                              aria-label={`Раскрыть: ${node.name}`}
                            >
                              <FaChevronRight aria-hidden />
                            </button>
                          ) : (
                            <span className="tree-leaf" aria-hidden />
                          )}
                          <Link
                            to={navigationPath(node)}
                            className="tree-link"
                            aria-current={isSelected ? "page" : undefined}
                            onClick={() => {
                              if (!node.has_children) return;
                              if (isSelected) toggle(node.id);
                              else setExpanded((c) => new Set([...c, node.id]));
                            }}
                          >
                            <span className="tree-name" title={node.path}>
                              {formatDepartmentName(node.name)}
                              {searching && node.ancestor_ids.length > 0 && (
                                <small>
                                  {node.path
                                    .split(" → ")
                                    .slice(0, -1)
                                    .join(" / ")}
                                </small>
                              )}
                            </span>
                            <span className="tree-count">
                              {node.total_staff_count.toLocaleString("ru-RU")}
                            </span>
                          </Link>
                        </div>
                      </motion.li>
                    );
                  })}
                </AnimatePresence>
              </ul>
            )}
          </div>
        </div>
        <div
          className="tree-resizer"
          role="separator"
          aria-orientation="vertical"
          aria-label="Ширина структуры"
          onPointerDown={startResize}
          onDoubleClick={() => {
            setTreeWidth(paneRef.current, 300);
            try {
              localStorage.removeItem(TREE_WIDTH_KEY);
            } catch {
              /* Nothing stored. */
            }
          }}
        />
      </aside>
    </>
  );
}
