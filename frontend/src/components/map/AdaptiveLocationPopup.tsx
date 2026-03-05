import React, { CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Map as LeafletMap, Point } from "leaflet";
import { FiMapPin, FiUsers, FiX } from "react-icons/fi";
import { LocationData } from "../../schemas/IData";

export type PopupPlacement =
  | "right"
  | "left"
  | "top"
  | "bottom"
  | "top-right"
  | "top-left";

type CandidatePlacement = PopupPlacement;

type PopupLayout = {
  placement: PopupPlacement;
  style: CSSProperties;
};

type PopupSizePreset = {
  width: number;
  estimatedHeight: number;
  maxHeight: number;
};

type CandidateScore = {
  placement: CandidatePlacement;
  left: number;
  top: number;
  overflowPx: number;
  score: number;
};

interface AdaptiveLocationPopupProps {
  map: LeafletMap | null;
  location: LocationData | null;
  locations: LocationData[];
  color: string;
  isDarkTheme: boolean;
  isKioskMode: boolean;
  isLandscape: boolean;
  mapZoom: number;
  viewportWidth: number;
  viewportHeight: number;
  onClose: () => void;
}

const POPUP_MARGIN = 10;
const MARKER_GAP = 22;
const POINT_OVERLAP_PADDING = 16;
const MARKER_OFFSCREEN_HIDE_MARGIN = 24;
const clamp = (value: number, min: number, max: number): number =>
  Math.max(min, Math.min(max, value));

const getEmployeesBadge = (value: number): string => {
  if (value > 999) return "999+";
  if (value > 99) return "99+";
  return String(Math.max(0, Math.floor(value)));
};

const getPopupSizePreset = (
  mapWidth: number,
  mapHeight: number,
  mapZoom: number,
  viewportHeight: number,
  isLandscape: boolean,
  isKioskMode: boolean,
): PopupSizePreset => {
  const zoomOutFactor = clamp((14.1 - mapZoom) / 4.3, 0, 1);
  const compactScale = 1 - zoomOutFactor * 0.28;
  const shortLandscape = isLandscape && mapHeight <= 320;
  const compactByHeight = mapHeight <= 430 || viewportHeight <= 500;
  const compactByWidth = mapWidth <= 520;
  const compact = compactByHeight || compactByWidth;

  if (compact) {
    const baseWidth = shortLandscape
      ? Math.min(252, Math.max(176, mapWidth - 30))
      : Math.min(282, Math.max(198, mapWidth - 22));
    const width = Math.round(baseWidth * (1 - zoomOutFactor * 0.24));
    const baseMaxHeight = shortLandscape
      ? Math.min(180, Math.max(118, mapHeight - 24))
      : Math.min(206, Math.max(138, mapHeight - 24));
    const maxHeight = Math.round(baseMaxHeight * (1 - zoomOutFactor * 0.2));
    const estimatedHeightBase = shortLandscape ? 146 : isLandscape ? 160 : 176;
    const estimatedHeight = Math.round(
      estimatedHeightBase * (1 - zoomOutFactor * 0.2),
    );
    return {
      width,
      estimatedHeight: Math.max(shortLandscape ? 116 : 128, estimatedHeight),
      maxHeight,
    };
  }

  const baseWidth = isLandscape
    ? Math.min(322, Math.max(220, mapWidth * 0.32))
    : Math.min(344, Math.max(238, mapWidth * 0.33));
  const width = Math.round(baseWidth * compactScale);

  const baseMaxHeight = isKioskMode
    ? Math.min(290, Math.max(180, mapHeight - 28))
    : Math.min(320, Math.max(190, mapHeight - 34));
  const maxHeight = Math.round(baseMaxHeight * (1 - zoomOutFactor * 0.14));

  const estimatedHeightBase = isLandscape ? 188 : 212;
  return {
    width,
    estimatedHeight: Math.round(estimatedHeightBase * (1 - zoomOutFactor * 0.16)),
    maxHeight,
  };
};

const getCandidatePositions = (
  markerPoint: Point,
  popupWidth: number,
  popupHeight: number,
): Array<{ placement: CandidatePlacement; left: number; top: number }> => [
  {
    placement: "right",
    left: markerPoint.x + MARKER_GAP,
    top: markerPoint.y - popupHeight / 2,
  },
  {
    placement: "left",
    left: markerPoint.x - popupWidth - MARKER_GAP,
    top: markerPoint.y - popupHeight / 2,
  },
  {
    placement: "top",
    left: markerPoint.x - popupWidth / 2,
    top: markerPoint.y - popupHeight - MARKER_GAP,
  },
  {
    placement: "bottom",
    left: markerPoint.x - popupWidth / 2,
    top: markerPoint.y + MARKER_GAP,
  },
  {
    placement: "top-right",
    left: markerPoint.x + MARKER_GAP,
    top: markerPoint.y - popupHeight - MARKER_GAP,
  },
  {
    placement: "top-left",
    left: markerPoint.x - popupWidth - MARKER_GAP,
    top: markerPoint.y - popupHeight - MARKER_GAP,
  },
];

const calculateOverflowPx = (
  left: number,
  top: number,
  width: number,
  height: number,
  mapWidth: number,
  mapHeight: number,
): number => {
  const right = left + width;
  const bottom = top + height;
  const overflowLeft = Math.max(0, POPUP_MARGIN - left);
  const overflowTop = Math.max(0, POPUP_MARGIN - top);
  const overflowRight = Math.max(0, right - (mapWidth - POPUP_MARGIN));
  const overflowBottom = Math.max(0, bottom - (mapHeight - POPUP_MARGIN));
  return overflowLeft + overflowTop + overflowRight + overflowBottom;
};

const calculateOverlapPenalty = (
  left: number,
  top: number,
  width: number,
  height: number,
  activePoint: Point,
  allPoints: Point[],
): number => {
  const right = left + width;
  const bottom = top + height;
  const expandedLeft = left - POINT_OVERLAP_PADDING;
  const expandedTop = top - POINT_OVERLAP_PADDING;
  const expandedRight = right + POINT_OVERLAP_PADDING;
  const expandedBottom = bottom + POINT_OVERLAP_PADDING;

  let penalty = 0;

  for (const point of allPoints) {
    if (point.x === activePoint.x && point.y === activePoint.y) continue;

    const insideExpanded =
      point.x >= expandedLeft &&
      point.x <= expandedRight &&
      point.y >= expandedTop &&
      point.y <= expandedBottom;

    if (!insideExpanded) continue;

    const insideMain =
      point.x >= left && point.x <= right && point.y >= top && point.y <= bottom;

    if (insideMain) {
      const distanceToCenter = Math.hypot(
        point.x - (left + width / 2),
        point.y - (top + height / 2),
      );
      penalty += 12 + Math.max(0, 70 - distanceToCenter) * 0.18;
      continue;
    }

    penalty += 2.6;
  }

  return penalty;
};

const distancePointToRect = (
  point: Point,
  left: number,
  top: number,
  width: number,
  height: number,
): number => {
  const right = left + width;
  const bottom = top + height;
  const dx = Math.max(left - point.x, 0, point.x - right);
  const dy = Math.max(top - point.y, 0, point.y - bottom);
  return Math.hypot(dx, dy);
};

const calculateActivePointProximityPenalty = (
  left: number,
  top: number,
  width: number,
  height: number,
  activePoint: Point,
  mapZoom: number,
): number => {
  const distance = distancePointToRect(activePoint, left, top, width, height);
  const zoomFactor = clamp((mapZoom - 12.2) / 4.2, 0, 1);
  const clearRadius = 86 + zoomFactor * 34;
  if (distance >= clearRadius) return 0;
  const overlapDepth = clearRadius - distance;
  return 8 + overlapDepth * 0.72;
};

const scoreCandidate = (
  candidate: { placement: CandidatePlacement; left: number; top: number },
  popupWidth: number,
  popupHeight: number,
  mapWidth: number,
  mapHeight: number,
  activePoint: Point,
  allPoints: Point[],
  mapZoom: number,
): CandidateScore => {
  const overflowPx = calculateOverflowPx(
    candidate.left,
    candidate.top,
    popupWidth,
    popupHeight,
    mapWidth,
    mapHeight,
  );

  const overlapPenalty = calculateOverlapPenalty(
    candidate.left,
    candidate.top,
    popupWidth,
    popupHeight,
    activePoint,
    allPoints,
  );
  const activePointPenalty = calculateActivePointProximityPenalty(
    candidate.left,
    candidate.top,
    popupWidth,
    popupHeight,
    activePoint,
    mapZoom,
  );

  const centerDistancePenalty =
    Math.abs(candidate.left + popupWidth / 2 - activePoint.x) * 0.06 +
    Math.abs(candidate.top + popupHeight / 2 - activePoint.y) * 0.03;

  const score =
    overflowPx * 130 +
    overlapPenalty * 34 +
    activePointPenalty * 26 +
    centerDistancePenalty;

  return {
    placement: candidate.placement,
    left: candidate.left,
    top: candidate.top,
    overflowPx,
    score,
  };
};

const pickBestLayout = (
  map: LeafletMap,
  location: LocationData,
  locations: LocationData[],
  mapZoom: number,
  viewportHeight: number,
  isLandscape: boolean,
  isKioskMode: boolean,
): PopupLayout | null => {
  const mapSize = map.getSize();
  if (!mapSize?.x || !mapSize?.y) return null;

  const markerPoint = map.latLngToContainerPoint([location.lat, location.lng]);
  const isMarkerOutsideViewport =
    markerPoint.x < -MARKER_OFFSCREEN_HIDE_MARGIN ||
    markerPoint.y < -MARKER_OFFSCREEN_HIDE_MARGIN ||
    markerPoint.x > mapSize.x + MARKER_OFFSCREEN_HIDE_MARGIN ||
    markerPoint.y > mapSize.y + MARKER_OFFSCREEN_HIDE_MARGIN;
  if (isMarkerOutsideViewport) return null;

  const allPoints = locations.map((loc) =>
    map.latLngToContainerPoint([loc.lat, loc.lng]),
  );

  const popupPreset = getPopupSizePreset(
    mapSize.x,
    mapSize.y,
    mapZoom,
    viewportHeight,
    isLandscape,
    isKioskMode,
  );

  const candidates = getCandidatePositions(
    markerPoint,
    popupPreset.width,
    popupPreset.estimatedHeight,
  );

  const scoredCandidates = candidates.map((candidate) =>
    scoreCandidate(
      candidate,
      popupPreset.width,
      popupPreset.estimatedHeight,
      mapSize.x,
      mapSize.y,
      markerPoint,
      allPoints,
      mapZoom,
    ),
  );

  const bestCandidate = scoredCandidates.sort((a, b) => a.score - b.score)[0];
  if (!bestCandidate) return null;

  const clampedLeft = Math.min(
    Math.max(bestCandidate.left, POPUP_MARGIN),
    mapSize.x - popupPreset.width - POPUP_MARGIN,
  );
  const clampedTop = Math.min(
    Math.max(bestCandidate.top, POPUP_MARGIN),
    mapSize.y - popupPreset.estimatedHeight - POPUP_MARGIN,
  );

  return {
    placement: bestCandidate.placement,
    style: {
      left: Math.round(clampedLeft),
      top: Math.round(clampedTop),
      width: popupPreset.width,
      maxHeight: popupPreset.maxHeight,
    },
  };
};

const AdaptiveLocationPopup: React.FC<AdaptiveLocationPopupProps> = ({
  map,
  location,
  locations,
  color,
  isDarkTheme,
  isKioskMode,
  isLandscape,
  mapZoom,
  viewportWidth,
  viewportHeight,
  onClose,
}) => {
  const [layout, setLayout] = useState<PopupLayout | null>(null);
  const frameRef = useRef<number | null>(null);

  const normalizedName = useMemo(
    () => location?.name?.trim() || "Локация",
    [location],
  );
  const normalizedAddress = useMemo(
    () => location?.address?.trim() || "Адрес не указан",
    [location],
  );

  const recomputeLayout = useCallback(() => {
    if (!map || !location) {
      setLayout(null);
      return;
    }

    const nextLayout = pickBestLayout(
      map,
      location,
      locations,
      mapZoom,
      viewportHeight,
      isLandscape,
      isKioskMode,
    );

    setLayout(nextLayout);
  }, [isKioskMode, isLandscape, location, locations, map, viewportHeight, mapZoom]);

  const scheduleLayoutRecompute = useCallback(() => {
    if (frameRef.current !== null) {
      window.cancelAnimationFrame(frameRef.current);
    }

    frameRef.current = window.requestAnimationFrame(() => {
      frameRef.current = null;
      recomputeLayout();
    });
  }, [recomputeLayout]);

  useEffect(() => {
    scheduleLayoutRecompute();
  }, [scheduleLayoutRecompute, viewportWidth, viewportHeight, location, mapZoom]);

  useEffect(() => {
    if (!map) return undefined;

    const handleMapMutation = () => {
      scheduleLayoutRecompute();
    };

    map.on("move", handleMapMutation);
    map.on("zoom", handleMapMutation);
    map.on("resize", handleMapMutation);

    return () => {
      map.off("move", handleMapMutation);
      map.off("zoom", handleMapMutation);
      map.off("resize", handleMapMutation);
    };
  }, [map, scheduleLayoutRecompute]);

  useEffect(() => {
    return () => {
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current);
      }
    };
  }, []);

  if (!location || !layout) return null;

  const themeClass = isDarkTheme ? "is-dark" : "is-light";
  const placementClass = `map-adaptive-popup--${layout.placement}`;

  return (
    <div className="map-adaptive-popup-layer" role="dialog" aria-live="polite">
      <div
        className={`map-adaptive-popup ${themeClass} ${placementClass}`}
        style={{
          ...layout.style,
          borderColor: `${color}66`,
          boxShadow: `0 18px 42px -24px ${isDarkTheme ? "rgba(15,23,42,0.95)" : "rgba(15,23,42,0.42)"}`,
        }}
      >
        <button
          type="button"
          onClick={onClose}
          className="map-adaptive-popup__close"
          aria-label="Закрыть информацию о точке"
        >
          <FiX className="w-4 h-4" />
        </button>

        <div className="map-adaptive-popup__head">
          <h2 className="map-adaptive-popup__title" title={normalizedName}>
            {normalizedName}
          </h2>
          <span
            className="map-adaptive-popup__badge"
            style={{
              borderColor: `${color}66`,
              color,
              backgroundColor: `${color}22`,
            }}
          >
            {getEmployeesBadge(location.employees)}
          </span>
        </div>

        <div className="map-adaptive-popup__address-wrap">
          <FiMapPin className="map-adaptive-popup__address-icon" />
          <p className="map-adaptive-popup__address" title={normalizedAddress}>
            {normalizedAddress}
          </p>
        </div>

        <div className="map-adaptive-popup__stats">
          <div className="map-adaptive-popup__stats-label">
            <FiUsers className="w-3.5 h-3.5" />
            Посещения
          </div>
          <div className="map-adaptive-popup__stats-value" style={{ color }}>
            {location.employees}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdaptiveLocationPopup;
