import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { createPortal } from "react-dom";
import {
  Map as LibreMap,
  Marker,
  LngLatBounds,
  NavigationControl,
  setWorkerUrl,
} from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import { FiLayers } from "react-icons/fi";
import { applyMapTheme, BASEMAP_STYLE } from "./mapTheme";
import {
  groupMapPoints,
  MAP_NUMBER,
  type MapEntry,
  type MapGroup,
} from "./mapModel";

setWorkerUrl(workerUrl);

export type AttendanceMapHandle = {
  showAll: () => void;
  focus: (entry: MapEntry) => void;
  retry: () => void;
};

type Props = {
  entries: MapEntry[];
  selectedKey: string | null;
  dark: boolean;
  date: string;
  onSelect: (entry: MapEntry) => void;
  onGroup: (entries: MapEntry[]) => void;
  onError: (message: string | null) => void;
};

type PositionedGroup = MapGroup & { lngLat: [number, number] };

function MapLabel({
  map,
  group,
  selectedKey,
  onClick,
}: {
  map: LibreMap;
  group: PositionedGroup;
  selectedKey: string | null;
  onClick: () => void;
}) {
  const element = useMemo(() => document.createElement("div"), []);
  const marker = useRef<Marker | null>(null);
  const isGroup = group.entries.length > 1;
  const active = group.entries.some((entry) => entry.key === selectedKey);
  useEffect(() => {
    marker.current = new Marker({
      element,
      anchor: "bottom",
      subpixelPositioning: true,
    })
      .setLngLat(map.getCenter())
      .addTo(map);
    return () => {
      marker.current?.remove();
    };
  }, [map, element]);
  useEffect(() => {
    marker.current?.setLngLat(group.lngLat).setOffset(group.offset ?? [0, 0]);
    element.style.zIndex = active ? "2" : "1";
  }, [group.lngLat, group.offset, element, active]);
  const [offsetX, offsetY] = group.offset ?? [0, 0];
  return createPortal(
    <>
      {(offsetX !== 0 || offsetY !== 0) && (
        <svg className="atlas-marker-leader" aria-hidden="true">
          <line x1="0" y1="0" x2={-offsetX} y2={-offsetY} />
          <circle cx={-offsetX} cy={-offsetY} r="3" />
        </svg>
      )}
      <button
        type="button"
        className={`atlas-marker ${isGroup ? "is-group" : ""} ${active ? "is-selected" : ""}`}
        style={{ "--location-color": group.entries[0].color } as CSSProperties}
        aria-label={
          isGroup
            ? `${group.entries.length} локаций, ${MAP_NUMBER.format(group.visits)} посещений. Раскрыть группу`
            : `${group.entries[0].name}. Посещений: ${group.visits}`
        }
        aria-pressed={active}
        title={
          isGroup ? "Приблизить и раскрыть локации" : group.entries[0].name
        }
        onClick={(event) => {
          event.stopPropagation();
          onClick();
        }}
      >
        <span className="atlas-marker__dot" aria-hidden="true" />
        <strong>{MAP_NUMBER.format(group.visits)}</strong>
        {isGroup && (
          <span className="atlas-marker__group">
            <FiLayers aria-hidden="true" />
            {group.entries.length}
          </span>
        )}
      </button>
    </>,
    element,
  );
}

const AttendanceMap = forwardRef<AttendanceMapHandle, Props>(
  function AttendanceMap(
    { entries, selectedKey, dark, date, onSelect, onGroup, onError },
    ref,
  ) {
    const container = useRef<HTMLDivElement>(null);
    const [map, setMap] = useState<LibreMap | null>(null);
    const [groups, setGroups] = useState<PositionedGroup[]>([]);
    const entriesRef = useRef(entries);
    const selectedRef = useRef(selectedKey);
    const themeRef = useRef(dark);
    const errorRef = useRef(onError);
    const initialFitDate = useRef<string | null>(null);
    const reducedMotion = (): boolean =>
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    entriesRef.current = entries;
    selectedRef.current = selectedKey;
    themeRef.current = dark;
    errorRef.current = onError;

    const showAll = useCallback((target: LibreMap, points: MapEntry[]) => {
      if (!points.length) return;
      const bounds = points.reduce(
        (result, entry) => result.extend([entry.lng, entry.lat]),
        new LngLatBounds(),
      );
      const narrow = target.getContainer().clientWidth < 600;
      target.fitBounds(bounds, {
        padding: narrow ? 52 : 90,
        maxZoom: points.length === 1 ? 14.8 : 14.2,
        duration: reducedMotion() ? 0 : 650,
      });
    }, []);

    useImperativeHandle(
      ref,
      () => ({
        showAll: () => {
          if (map) showAll(map, entriesRef.current);
        },
        focus: (entry) => {
          map?.easeTo({
            center: [entry.lng, entry.lat],
            zoom: Math.max(map.getZoom(), 16),
            padding: { top: 60, bottom: 145, left: 60, right: 60 },
            duration: reducedMotion() ? 0 : 550,
          });
        },
        retry: () => {
          map?.setStyle(BASEMAP_STYLE, { diff: false });
        },
      }),
      [map, showAll],
    );

    useEffect(() => {
      if (!container.current) return;
      let instance: LibreMap;
      try {
        instance = new LibreMap({
          container: container.current,
          style: BASEMAP_STYLE,
          center: [76.9286, 43.2389],
          zoom: 11,
          maxZoom: 18,
          minZoom: 3,
          pitchWithRotate: false,
          dragRotate: false,
          attributionControl: { compact: false },
          locale: {
            "NavigationControl.ZoomIn": "Приблизить",
            "NavigationControl.ZoomOut": "Отдалить",
            "AttributionControl.ToggleAttribution": "Источники карты",
            "Map.Title": "Карта посещаемости",
          },
        });
      } catch {
        errorRef.current(
          "Карта недоступна на этом устройстве. Локации можно открыть в списке.",
        );
        return;
      }
      instance.addControl(
        new NavigationControl({ showCompass: false }),
        "bottom-right",
      );
      instance.touchZoomRotate.disableRotation();
      const regroup = (): void => {
        const width = instance.getContainer().clientWidth;
        const height = instance.getContainer().clientHeight;
        const points = entriesRef.current
          .map((entry) => ({
            entry,
            ...instance.project([entry.lng, entry.lat]),
          }))
          .filter(
            (point) =>
              point.x >= -60 &&
              point.y >= -60 &&
              point.x <= width + 60 &&
              point.y <= height + 60,
          );
        setGroups(
          groupMapPoints(points, window.innerWidth >= 2560 ? 1.4 : 1, {
            selectedKey: selectedRef.current,
            spread: instance.getZoom() >= 15,
          }).map((group) => {
            const coordinate = instance.unproject([group.x, group.y]);
            return { ...group, lngLat: [coordinate.lng, coordinate.lat] };
          }),
        );
      };
      instance.on("style.load", () => {
        applyMapTheme(instance, themeRef.current);
        errorRef.current(null);
      });
      instance.on("error", () => {
        errorRef.current(
          "Не удалось загрузить часть карты. Проверьте соединение или повторите загрузку.",
        );
      });
      instance.on("idle", () => {
        errorRef.current(null);
      });
      instance.on("moveend", regroup);
      instance.on("resize", regroup);
      const observer = new ResizeObserver(() => instance.resize());
      observer.observe(container.current);
      instance.on("load", regroup);
      setMap(instance);
      return () => {
        observer.disconnect();
        instance.remove();
      };
    }, []);

    useEffect(() => {
      if (map?.getStyle()?.layers.length) applyMapTheme(map, dark);
    }, [map, dark]);

    useEffect(() => {
      if (!map) return;
      if (initialFitDate.current !== date && entries.length) {
        initialFitDate.current = date;
        showAll(map, entries);
      } else {
        map.fire("moveend");
      }
    }, [date, entries, map, selectedKey, showAll]);

    return (
      <>
        <div ref={container} className="atlas-map" aria-label="Карта локаций" />
        {map &&
          groups.map((group) => (
            <MapLabel
              key={group.entries
                .map((entry) => entry.key)
                .sort()
                .join(";")}
              map={map}
              group={group}
              selectedKey={selectedKey}
              onClick={() => {
                if (group.entries.length === 1) {
                  onSelect(group.entries[0]);
                  return;
                }
                const first = group.entries[0];
                const samePosition = group.entries.every(
                  (entry) =>
                    Math.abs(entry.lat - first.lat) +
                      Math.abs(entry.lng - first.lng) <
                    0.00001,
                );
                if (samePosition || map.getZoom() >= 17.5) {
                  onGroup(group.entries);
                  return;
                }
                map.easeTo({
                  center: group.lngLat,
                  zoom: Math.min(18, map.getZoom() + 1.5),
                  duration: reducedMotion() ? 0 : 500,
                });
              }}
            />
          ))}
      </>
    );
  },
);

export default AttendanceMap;
