import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import {
  FiCalendar,
  FiChevronLeft,
  FiChevronRight,
  FiCrosshair,
  FiLayers,
  FiList,
  FiMapPin,
  FiMaximize,
  FiMinimize,
  FiRefreshCw,
  FiSearch,
  FiUsers,
  FiX,
} from "react-icons/fi";
import EditableDateField from "../components/EditableDateField";
import AttendanceMap, {
  type AttendanceMapHandle,
} from "../components/map/AttendanceMap";
import {
  MAP_NUMBER,
  matchesMapQuery,
  type MapEntry,
} from "../components/map/mapModel";
import { useMapLocations } from "../hooks/useMapLocations";
import { useMapDisplay } from "../hooks/useMapDisplay";
import "../components/map/map-dashboard.css";

export default function MapDashboard() {
  const { date, setDate, entries, loaded, busy, error, refresh } =
    useMapLocations();
  const { dark, kiosk, fullscreenBusy, toggleFullscreen, displayError } =
    useMapDisplay();
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [groupKeys, setGroupKeys] = useState<string[] | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const map = useRef<AttendanceMapHandle>(null);
  const root = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const listButton = useRef<HTMLButtonElement>(null);
  const detail = useRef<HTMLDivElement>(null);
  const focusDetailAfterSelection = useRef(false);
  const restoreListFocus = useRef(false);
  const selected = entries.find((entry) => entry.key === selectedKey) ?? null;
  const visits = entries.reduce((total, entry) => total + entry.employees, 0);
  const filtered = useMemo(
    () =>
      entries
        .filter(
          (entry) =>
            matchesMapQuery(entry, query) &&
            (!groupKeys || groupKeys.includes(entry.key)),
        )
        .sort(
          (a, b) =>
            b.employees - a.employees || a.name.localeCompare(b.name, "ru"),
        ),
    [entries, groupKeys, query],
  );
  const selectedIndex = filtered.findIndex(
    (entry) => entry.key === selectedKey,
  );

  useEffect(() => {
    const updateHeight = (): void => {
      if (!root.current) return;
      const top = Math.max(0, root.current.getBoundingClientRect().top);
      const mobileDock = document.querySelector('nav[aria-label="Навигация"]');
      const reserve =
        !kiosk && window.innerWidth < 900
          ? (mobileDock?.getBoundingClientRect().height ?? 72) + 16
          : kiosk
            ? 0
            : 28;
      root.current.style.setProperty(
        "--atlas-height",
        `${Math.max(440, (window.visualViewport?.height ?? window.innerHeight) - top - reserve)}px`,
      );
    };
    updateHeight();
    window.addEventListener("resize", updateHeight);
    window.visualViewport?.addEventListener("resize", updateHeight);
    return () => {
      window.removeEventListener("resize", updateHeight);
      window.visualViewport?.removeEventListener("resize", updateHeight);
    };
  }, [kiosk]);

  useEffect(() => {
    if (panelOpen) search.current?.focus();
  }, [panelOpen]);

  useEffect(() => {
    const syncPanel = (): void => {
      if (stage.current)
        stage.current.inert = panelOpen && window.innerWidth <= 700;
    };
    syncPanel();
    if (!panelOpen) {
      if (focusDetailAfterSelection.current && selectedKey)
        detail.current?.focus();
      else if (restoreListFocus.current) listButton.current?.focus();
      focusDetailAfterSelection.current = false;
      restoreListFocus.current = false;
    }
    window.addEventListener("resize", syncPanel);
    return () => window.removeEventListener("resize", syncPanel);
  }, [panelOpen, selectedKey]);

  const select = (entry: MapEntry): void => {
    focusDetailAfterSelection.current = panelOpen;
    setSelectedKey(entry.key);
    map.current?.focus(entry);
    setPanelOpen(false);
  };
  const closePanel = (): void => {
    restoreListFocus.current = true;
    setPanelOpen(false);
  };
  const closeDetail = (): void => {
    setSelectedKey(null);
    if (panelOpen) search.current?.focus();
    else listButton.current?.focus();
  };
  const resetView = (): void => {
    setQuery("");
    setGroupKeys(null);
    setSelectedKey(null);
    map.current?.showAll();
  };
  const changeDate = (value: string): void => {
    setSelectedKey(null);
    setGroupKeys(null);
    setQuery("");
    setDate(value);
  };

  return (
    <section
      ref={root}
      className={`atlas ${kiosk ? "atlas--kiosk" : ""}`}
      aria-label="Карта посещаемости"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          if (selectedKey) closeDetail();
          else if (panelOpen) closePanel();
        }
      }}
    >
      <header className="atlas-header">
        <div className="atlas-heading">
          <span className="atlas-brand-icon" aria-hidden="true">
            <FiMapPin />
          </span>
          <h1>Карта посещаемости</h1>
        </div>
        <div
          className="atlas-summary"
          aria-label={`${MAP_NUMBER.format(visits)} посещений в ${entries.length} локациях`}
        >
          <div>
            <FiUsers aria-hidden="true" />
            <strong>{loaded ? MAP_NUMBER.format(visits) : "—"}</strong>
            <span>посещений</span>
          </div>
          <span className="atlas-summary__divider" aria-hidden="true" />
          <div>
            <FiMapPin aria-hidden="true" />
            <strong>{loaded ? MAP_NUMBER.format(entries.length) : "—"}</strong>
            <span>локаций</span>
          </div>
        </div>
        <div className="atlas-header-actions">
          <EditableDateField
            value={date}
            onChange={(event) => changeDate(event.target.value)}
            startIcon={<FiCalendar aria-hidden="true" />}
            ariaLabel="Дата посещаемости"
            containerClassName="atlas-date"
            displayClassName="atlas-button atlas-date__button"
          />
          <button
            type="button"
            className="atlas-button atlas-button--icon"
            onClick={() => void refresh()}
            disabled={busy}
            aria-label="Обновить данные"
            title="Обновить данные"
          >
            <FiRefreshCw
              className={busy ? "atlas-refreshing" : ""}
              aria-hidden="true"
            />
          </button>
          <button
            type="button"
            className="atlas-button atlas-button--screen"
            disabled={fullscreenBusy}
            onClick={() => void toggleFullscreen()}
            aria-label={
              kiosk ? "Выйти из режима экрана" : "Полноэкранный режим"
            }
          >
            {kiosk ? (
              <FiMinimize aria-hidden="true" />
            ) : (
              <FiMaximize aria-hidden="true" />
            )}
            <span>{kiosk ? "Выйти" : "На весь экран"}</span>
          </button>
        </div>
      </header>

      <div className={`atlas-workspace ${panelOpen ? "has-panel" : ""}`}>
        {panelOpen && (
          <aside
            id="map-location-list"
            className="atlas-panel"
            aria-label="Список локаций"
          >
            <div className="atlas-panel__head">
              <h2>
                {groupKeys ? "Локации в группе" : "Локации"}
                <span>{filtered.length}</span>
              </h2>
              <button
                type="button"
                className="atlas-button atlas-button--icon"
                aria-label="Закрыть список локаций"
                onClick={closePanel}
              >
                <FiX aria-hidden="true" />
              </button>
            </div>
            <label className="atlas-search">
              <FiSearch aria-hidden="true" />
              <input
                ref={search}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Название или адрес"
                aria-label="Найти локацию"
              />
              {query && (
                <button
                  type="button"
                  aria-label="Очистить поиск"
                  onClick={() => {
                    setQuery("");
                    search.current?.focus();
                  }}
                >
                  <FiX aria-hidden="true" />
                </button>
              )}
            </label>
            {groupKeys && (
              <button
                type="button"
                className="atlas-back"
                onClick={() => {
                  setGroupKeys(null);
                  setQuery("");
                }}
              >
                <FiChevronLeft aria-hidden="true" />
                Все локации
              </button>
            )}
            <div className="atlas-panel__caption">
              <span>Локация</span>
              <span>посещений</span>
            </div>
            <ul className="atlas-location-list">
              {filtered.map((entry) => (
                <li key={entry.key}>
                  <button
                    type="button"
                    className={`atlas-location ${selectedKey === entry.key ? "is-selected" : ""}`}
                    aria-pressed={selectedKey === entry.key}
                    onClick={() => select(entry)}
                    style={{ "--location-color": entry.color } as CSSProperties}
                  >
                    <span className="atlas-location__dot" aria-hidden="true" />
                    <span className="atlas-location__text">
                      <strong>{entry.name || "Без названия"}</strong>
                      <span>{entry.address || "Адрес не указан"}</span>
                    </span>
                    <strong className="atlas-location__value">
                      {MAP_NUMBER.format(entry.employees)}
                    </strong>
                  </button>
                </li>
              ))}
            </ul>
            {!filtered.length && (
              <div className="atlas-panel__empty">
                {query
                  ? "Локации не найдены. Попробуйте другое название или адрес."
                  : "На выбранную дату нет посещений."}
              </div>
            )}
          </aside>
        )}

        <div ref={stage} className="atlas-stage">
          <AttendanceMap
            ref={map}
            entries={entries}
            selectedKey={selectedKey}
            dark={dark}
            date={date}
            onSelect={select}
            onGroup={(group) => {
              setSelectedKey(null);
              setGroupKeys(group.map((entry) => entry.key));
              setQuery("");
              setPanelOpen(true);
            }}
            onError={setMapError}
          />
          <div className="atlas-map-tools">
            <button
              ref={listButton}
              type="button"
              className={`atlas-button ${panelOpen ? "is-active" : ""}`}
              aria-expanded={panelOpen}
              aria-controls="map-location-list"
              onClick={() => (panelOpen ? closePanel() : setPanelOpen(true))}
            >
              <FiList aria-hidden="true" />
              <span>Локации</span>
            </button>
            <button
              type="button"
              className="atlas-button"
              onClick={resetView}
              disabled={!entries.length}
            >
              <FiLayers aria-hidden="true" />
              <span>Все точки</span>
            </button>
          </div>
          {busy && !loaded && (
            <div className="atlas-state" role="status">
              <span className="atlas-state__symbol">
                <FiRefreshCw className="atlas-refreshing" aria-hidden="true" />
              </span>
              <strong>Загружаем посещаемость</strong>
              <span>Локации появятся на карте</span>
            </div>
          )}
          {!busy && !error && loaded && !entries.length && (
            <div className="atlas-state">
              <span className="atlas-state__symbol">
                <FiMapPin aria-hidden="true" />
              </span>
              <strong>На эту дату нет посещений</strong>
              <span>Выберите другую дату в календаре</span>
            </div>
          )}
          {(error || mapError || displayError) && (
            <div className="atlas-notice" role="status">
              <span>{error ?? mapError ?? displayError}</span>
              <button
                type="button"
                onClick={() => {
                  if (error) void refresh();
                  else if (displayError && !mapError) void toggleFullscreen();
                  else map.current?.retry();
                }}
              >
                Повторить
              </button>
            </div>
          )}
          {selected && (
            <div
              ref={detail}
              tabIndex={-1}
              role="region"
              className="atlas-detail"
              aria-label="Выбранная локация"
              style={{ "--location-color": selected.color } as CSSProperties}
            >
              <div className="atlas-detail__identity">
                <span className="atlas-detail__pin" aria-hidden="true">
                  <FiMapPin />
                </span>
                <div>
                  <h2>{selected.name || "Без названия"}</h2>
                  <p>
                    <FiMapPin aria-hidden="true" />
                    {selected.address || "Адрес не указан"}
                  </p>
                </div>
              </div>
              <div className="atlas-detail__visits">
                <strong>{MAP_NUMBER.format(selected.employees)}</strong>
                <span>посещений</span>
              </div>
              <div className="atlas-detail__actions">
                <span className="atlas-detail__position">
                  {selectedIndex >= 0
                    ? `${selectedIndex + 1} / ${filtered.length}`
                    : ""}
                </span>
                <button
                  type="button"
                  className="atlas-button atlas-button--icon"
                  aria-label="Предыдущая локация"
                  disabled={selectedIndex <= 0}
                  onClick={() => select(filtered[selectedIndex - 1])}
                >
                  <FiChevronLeft aria-hidden="true" />
                </button>
                <button
                  type="button"
                  className="atlas-button atlas-button--icon"
                  aria-label="Следующая локация"
                  disabled={
                    selectedIndex < 0 || selectedIndex >= filtered.length - 1
                  }
                  onClick={() => select(filtered[selectedIndex + 1])}
                >
                  <FiChevronRight aria-hidden="true" />
                </button>
                <button
                  type="button"
                  className="atlas-button atlas-button--icon"
                  aria-label="Приблизить выбранную локацию"
                  onClick={() => map.current?.focus(selected)}
                >
                  <FiCrosshair aria-hidden="true" />
                </button>
                <button
                  type="button"
                  className="atlas-button atlas-button--icon"
                  aria-label="Закрыть информацию о локации"
                  onClick={closeDetail}
                >
                  <FiX aria-hidden="true" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
