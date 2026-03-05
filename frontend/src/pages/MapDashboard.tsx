import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { MapContainer, TileLayer, useMap, useMapEvents, ZoomControl } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L, { Map as LeafletMap } from "leaflet";
import { useLocation, useNavigate } from "react-router-dom";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import Notification from "../components/Notification";
import AnimatedMarker from "../components/AnimatedMarker";
import AdaptiveLocationPopup from "../components/map/AdaptiveLocationPopup";
import { BaseAction } from "../schemas/BaseAction";
import { LocationData } from "../schemas/IData";
import { FaCalendarAlt, FaCompress, FaExpand } from "react-icons/fa";
import { FiClock, FiCrosshair, FiMapPin, FiMaximize2, FiUsers } from "react-icons/fi";
import { motion, Variants } from "framer-motion";
import LoaderComponent from "../components/LoaderComponent";
import EditableDateField from "../components/EditableDateField";
import { useAppSelector } from "../store/hooks";
import useWindowSize from "../hooks/useWindowSize";

type MapDispatchPayload = boolean | LocationData[] | string;
type MapFocusMode = "first" | "all";
type Rgb = { r: number; g: number; b: number };
type PaletteColor = {
  hex: string;
  lab: [number, number, number];
};

type KeyedLocation = {
  key: string;
  location: LocationData;
  index: number;
};

interface DocumentWithFullscreen extends Document {
  webkitExitFullscreen?: () => Promise<void> | void;
  mozCancelFullScreen?: () => Promise<void> | void;
  msExitFullscreen?: () => Promise<void> | void;
  webkitFullscreenElement?: Element | null;
  mozFullScreenElement?: Element | null;
  msFullscreenElement?: Element | null;
}

interface DocumentElementWithFullscreen extends HTMLElement {
  webkitRequestFullscreen?: () => Promise<void> | void;
  mozRequestFullScreen?: () => Promise<void> | void;
  msRequestFullscreen?: () => Promise<void> | void;
}

const MAP_DEFAULT_CENTER: [number, number] = [54.328962, 48.389899];
const MAP_DEFAULT_ZOOM = 13.4;
const MAP_MULTI_POINT_ZOOM = 15.1;
const MAP_FIRST_FOCUS_MIN_ZOOM = 13.3;
const MAP_FIRST_FOCUS_MAX_ZOOM = 16.2;
const MAP_COLOR_BASE_RADIUS_METERS = 64;
const MAP_RETRY_SYNC_ATTEMPTS = 30;
const MAP_RETRY_SYNC_INTERVAL_MS = 120;
const NUMBER_FORMATTER = new Intl.NumberFormat("ru-RU");
const MOBILE_DOCK_QUERY = 'nav[aria-label="Навигация"]';
const MOBILE_DOCK_FALLBACK_HEIGHT = 58;

const OSM_TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

const DISTINCT_HEX_COLORS_LIGHT = [
  "#DC2626",
  "#1E3A8A",
  "#9F1239",
  "#0F766E",
  "#7E22CE",
  "#92400E",
  "#155E75",
  "#7C2D12",
  "#1D4ED8",
  "#B91C1C",
  "#6D28D9",
  "#065F46",
  "#C2410C",
  "#7F1D1D",
  "#0C4A6E",
  "#4C1D95",
  "#A21CAF",
  "#134E4A",
  "#991B1B",
  "#1E40AF",
  "#BE123C",
  "#166534",
  "#7C3AED",
  "#0E7490",
  "#EA580C",
  "#5B21B6",
  "#7F1D1D",
  "#0F766E",
  "#4338CA",
  "#9A3412",
  "#831843",
  "#0369A1",
  "#166534",
  "#7E22CE",
  "#B91C1C",
  "#1D4ED8",
  "#6D28D9",
  "#C026D3",
  "#115E59",
  "#BE185D",
  "#374151",
  "#0891B2",
  "#A16207",
  "#0369A1",
  "#4D7C0F",
  "#9D174D",
  "#312E81",
  "#78350F",
];

const DISTINCT_HEX_COLORS_DARK = [
  "#F87171",
  "#93C5FD",
  "#FB7185",
  "#2DD4BF",
  "#C4B5FD",
  "#FDBA74",
  "#67E8F9",
  "#FDBA74",
  "#60A5FA",
  "#FCA5A5",
  "#A78BFA",
  "#34D399",
  "#FB923C",
  "#FDA4AF",
  "#38BDF8",
  "#C4B5FD",
  "#E879F9",
  "#5EEAD4",
  "#F87171",
  "#93C5FD",
  "#FB7185",
  "#4ADE80",
  "#A78BFA",
  "#67E8F9",
  "#FDBA74",
  "#C4B5FD",
  "#FCA5A5",
  "#2DD4BF",
  "#818CF8",
  "#FDBA74",
  "#F9A8D4",
  "#7DD3FC",
  "#86EFAC",
  "#C4B5FD",
  "#F87171",
  "#93C5FD",
  "#A78BFA",
  "#E879F9",
  "#5EEAD4",
  "#F472B6",
  "#D1D5DB",
  "#67E8F9",
  "#FDE68A",
  "#7DD3FC",
  "#A3E635",
  "#F9A8D4",
  "#A5B4FC",
  "#FCD34D",
];

const getFormattedDateAt = (): string => {
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  return yesterday.toISOString().split("T")[0];
};

const calculateDistanceMeters = (
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number => {
  const latMidRad = (((lat1 + lat2) / 2) * Math.PI) / 180;
  const mPerDegLat = 111320;
  const mPerDegLon = 111320 * Math.cos(latMidRad);
  const dy = (lat2 - lat1) * mPerDegLat;
  const dx = (lon2 - lon1) * mPerDegLon;
  return Math.sqrt(dx * dx + dy * dy);
};

const estimateLocationRadiusMeters = (): number => MAP_COLOR_BASE_RADIUS_METERS;

const hexToRgb = (hex: string): Rgb => {
  const value = hex.replace("#", "").trim();
  if (value.length !== 6) return { r: 59, g: 130, b: 246 };
  return {
    r: parseInt(value.slice(0, 2), 16),
    g: parseInt(value.slice(2, 4), 16),
    b: parseInt(value.slice(4, 6), 16),
  };
};

const srgbToLinear = (channel: number): number => {
  const x = channel / 255;
  return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
};

const labPivot = (value: number): number =>
  value > 0.008856 ? Math.cbrt(value) : 7.787 * value + 16 / 116;

const rgbToLab = ({ r, g, b }: Rgb): [number, number, number] => {
  const rl = srgbToLinear(r);
  const gl = srgbToLinear(g);
  const bl = srgbToLinear(b);
  const x = rl * 0.4124 + gl * 0.3576 + bl * 0.1805;
  const y = rl * 0.2126 + gl * 0.7152 + bl * 0.0722;
  const z = rl * 0.0193 + gl * 0.1192 + bl * 0.9505;
  const fx = labPivot(x / 0.95047);
  const fy = labPivot(y / 1);
  const fz = labPivot(z / 1.08883);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
};

const labDistance = (
  a: [number, number, number],
  b: [number, number, number],
): number => {
  const dl = a[0] - b[0];
  const da = a[1] - b[1];
  const db = a[2] - b[2];
  return Math.sqrt(dl * dl + da * da + db * db);
};

const buildPalette = (hexColors: string[]): PaletteColor[] =>
  hexColors.map((hex) => ({
    hex,
    lab: rgbToLab(hexToRgb(hex)),
  }));

const MAP_PALETTE_LIGHT = buildPalette(DISTINCT_HEX_COLORS_LIGHT);
const MAP_PALETTE_DARK = buildPalette(DISTINCT_HEX_COLORS_DARK);
const MAP_PALETTE_LIGHT_DISTANCE = MAP_PALETTE_LIGHT.map((a) =>
  MAP_PALETTE_LIGHT.map((b) => labDistance(a.lab, b.lab)),
);
const MAP_PALETTE_DARK_DISTANCE = MAP_PALETTE_DARK.map((a) =>
  MAP_PALETTE_DARK.map((b) => labDistance(a.lab, b.lab)),
);

const assignHighContrastColors = (
  locations: LocationData[],
  palette: PaletteColor[],
  paletteDistance: number[][],
): string[] => {
  const numLocations = locations.length;
  if (numLocations === 0) return [];

  const edges: { to: number; weight: number }[][] = Array.from(
    { length: numLocations },
    () => [],
  );
  const weightedDegree = new Array(numLocations).fill(0);
  const effectiveRadii = locations.map(() => estimateLocationRadiusMeters());

  for (let i = 0; i < numLocations; i++) {
    for (let j = i + 1; j < numLocations; j++) {
      const distanceM = calculateDistanceMeters(
        locations[i].lat,
        locations[i].lng,
        locations[j].lat,
        locations[j].lng,
      );
      const overlapGap = distanceM - (effectiveRadii[i] + effectiveRadii[j]);
      let weight = 0;

      if (overlapGap <= 0) weight = 14;
      else if (overlapGap <= 40) weight = 11;
      else if (overlapGap <= 90) weight = 9;
      else if (overlapGap <= 180) weight = 7;
      else if (distanceM <= 300) weight = 5;
      else if (distanceM <= 700) weight = 3;
      else if (distanceM <= 1100) weight = 1;

      if (weight > 0) {
        edges[i].push({ to: j, weight });
        edges[j].push({ to: i, weight });
        weightedDegree[i] += weight;
        weightedDegree[j] += weight;
      }
    }
  }

  const paletteCount = palette.length;
  const assigned = new Array(numLocations).fill(-1);
  const usageCount = new Array(paletteCount).fill(0);

  for (let step = 0; step < numLocations; step++) {
    let picked = -1;
    let bestSaturation = -1;
    let bestDegree = -1;

    for (let i = 0; i < numLocations; i++) {
      if (assigned[i] !== -1) continue;
      const neighborColors = new Set<number>();
      for (const edge of edges[i]) {
        const colorIdx = assigned[edge.to];
        if (colorIdx !== -1) neighborColors.add(colorIdx);
      }
      const saturation = neighborColors.size;
      const degree = weightedDegree[i];
      if (
        saturation > bestSaturation ||
        (saturation === bestSaturation && degree > bestDegree) ||
        (saturation === bestSaturation && degree === bestDegree && i < picked)
      ) {
        picked = i;
        bestSaturation = saturation;
        bestDegree = degree;
      }
    }

    if (picked === -1) break;

    let bestColor = 0;
    let bestScore = Number.NEGATIVE_INFINITY;

    for (let colorIdx = 0; colorIdx < paletteCount; colorIdx++) {
      let score = -usageCount[colorIdx] * 11;
      for (const edge of edges[picked]) {
        const neighborColor = assigned[edge.to];
        if (neighborColor === -1) continue;
        if (neighborColor === colorIdx) {
          score -= 7200 * edge.weight;
        } else {
          score += paletteDistance[colorIdx][neighborColor] * edge.weight;
        }
      }
      score += ((picked * 17 + colorIdx * 11) % 19) * 0.01;
      if (score > bestScore) {
        bestScore = score;
        bestColor = colorIdx;
      }
    }

    assigned[picked] = bestColor;
    usageCount[bestColor] += 1;
  }

  return locations.map((_, index) => {
    const colorIndex =
      assigned[index] >= 0 ? assigned[index] : index % palette.length;
    return palette[colorIndex].hex;
  });
};

const normalizeLocationKeyPart = (value: string): string =>
  value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ");

const buildLocationStableKey = (location: LocationData): string =>
  [
    normalizeLocationKeyPart(location.name || ""),
    normalizeLocationKeyPart(location.address || ""),
    location.lat.toFixed(6),
    location.lng.toFixed(6),
  ].join("|");

const createStableLocationKeys = (locations: LocationData[]): string[] => {
  const seen = new Map<string, number>();

  return locations.map((location) => {
    const base = buildLocationStableKey(location);
    const nextIndex = (seen.get(base) ?? 0) + 1;
    seen.set(base, nextIndex);
    return nextIndex === 1 ? base : `${base}::${nextIndex}`;
  });
};

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: 0.5, ease: "easeOut" },
  },
  exit: { opacity: 0, transition: { duration: 0.3, ease: "easeIn" } },
};

const mapContainerVariants: Variants = {
  hidden: { opacity: 0, scale: 0.98 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { delay: 0.2, duration: 0.5, ease: "easeOut" },
  },
};

const dateVariants: Variants = {
  hidden: { opacity: 0, y: -20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { delay: 0.1, duration: 0.4 },
  },
};

const buttonVariants: Variants = {
  initial: { scale: 1 },
  hover: { scale: 1.05 },
  tap: { scale: 0.95 },
};

const useFullscreenChange = (callback: () => void) => {
  useEffect(() => {
    document.addEventListener("fullscreenchange", callback);
    document.addEventListener("webkitfullscreenchange", callback);
    document.addEventListener("mozfullscreenchange", callback);
    document.addEventListener("MSFullscreenChange", callback);

    return () => {
      document.removeEventListener("fullscreenchange", callback);
      document.removeEventListener("webkitfullscreenchange", callback);
      document.removeEventListener("mozfullscreenchange", callback);
      document.removeEventListener("MSFullscreenChange", callback);
    };
  }, [callback]);
};

const MapEventHandler: React.FC<{
  mapRef: React.MutableRefObject<LeafletMap | null>;
  onMapReady: () => void;
  onMapBackgroundClick: () => void;
  onMapViewportChange: (zoom: number) => void;
}> = ({ mapRef, onMapReady, onMapBackgroundClick, onMapViewportChange }) => {
  const map = useMap();

  useMapEvents({
    click: () => {
      onMapBackgroundClick();
    },
    zoomend: () => {
      onMapViewportChange(map.getZoom());
    },
    moveend: () => {
      onMapViewportChange(map.getZoom());
    },
  });

  useEffect(() => {
    mapRef.current = map;
    onMapViewportChange(map.getZoom());
    onMapReady();
  }, [map, mapRef, onMapReady, onMapViewportChange]);

  return null;
};

const MapDashboard: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const viewport = useWindowSize();
  const isKiosk =
    /\/map$/.test(location.pathname) &&
    new URLSearchParams(location.search).get("kiosk") === "1";
  const isLandscapeViewport = viewport.orientation === "landscape";
  const hasTouchInput = useMemo(() => {
    if (typeof window === "undefined") return false;
    return (
      navigator.maxTouchPoints > 0 ||
      window.matchMedia("(pointer: coarse)").matches
    );
  }, []);

  const isTvLikeDevice = useMemo(() => {
    if (typeof navigator === "undefined") return false;
    const userAgent = navigator.userAgent.toLowerCase();
    const hasTvUaHint =
      /(android tv|smart-tv|smarttv|googletv|hbbtv|webos|netcast|tizen|bravia|viera|aft)/.test(
        userAgent,
      );
    const isAndroidUa = userAgent.includes("android");
    const isLikelyTvViewport =
      isAndroidUa &&
      isLandscapeViewport &&
      viewport.width >= 900 &&
      viewport.width <= 1680 &&
      !hasTouchInput;

    return hasTvUaHint || isLikelyTvViewport;
  }, [hasTouchInput, isLandscapeViewport, viewport.width]);

  const viewportShortSide = Math.min(viewport.width, viewport.height);
  const isPhone = !isTvLikeDevice && viewport.width < 640;
  const isPhoneLikeLandscape =
    !isTvLikeDevice &&
    isLandscapeViewport &&
    viewportShortSide <= 430 &&
    viewport.aspectBucket !== "square-ish";
  const isPhoneViewportClass = isPhone || isPhoneLikeLandscape;
  const isTablet =
    !isTvLikeDevice && viewport.width >= 640 && viewport.width < 1024;
  const isMobileViewport = !isTvLikeDevice && viewport.width < 1024;
  const isPhoneLandscapeViewport = isLandscapeViewport && isPhoneViewportClass;
  const isUltraNarrowViewport =
    viewport.width <= 390 || viewport.aspectBucket === "portrait-tall";
  const isDenseHeaderViewport =
    isPhoneLandscapeViewport ||
    (isTablet && isLandscapeViewport && viewport.height <= 620);
  const isWideViewport =
    viewport.width >= 1536 || viewport.aspectBucket === "landscape-ultrawide";

  const [locations, setLocations] = useState<LocationData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [visiblePopupKey, setVisiblePopupKey] = useState<string | null>(null);
  const [isMarkersVisible, setIsMarkersVisible] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const isMapPriorityLayout =
    isPhoneLandscapeViewport &&
    viewport.height <= 560 &&
    (isKiosk || isFullscreen);
  const isKioskMobileViewport = isKiosk && isMobileViewport && !isFullscreen;
  const [isFullscreenBusy, setIsFullscreenBusy] = useState(false);
  const [mapReadyVersion, setMapReadyVersion] = useState(0);
  const [mapFocusMode, setMapFocusMode] = useState<MapFocusMode>("first");
  const [assignedColors, setAssignedColors] = useState<string[]>([]);
  const [dateAt, setDateAt] = useState<string>(getFormattedDateAt());
  const [lastRequestAt, setLastRequestAt] = useState<Date | null>(null);
  const [mapViewportHeight, setMapViewportHeight] = useState(560);
  const [mapZoom, setMapZoom] = useState(MAP_DEFAULT_ZOOM);
  const [isDarkTheme, setIsDarkTheme] = useState(() => {
    if (typeof document === "undefined") return false;
    return document.documentElement.classList.contains("dark");
  });

  const reportsAutoRefreshMinutes = useAppSelector(
    (state) => state.ui.reportsAutoRefreshMinutes,
  );

  const mapRef = useRef<LeafletMap | null>(null);
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapViewportRef = useRef<HTMLDivElement>(null);
  const controlsRef = useRef<HTMLDivElement>(null);
  const fullscreenToggleLockRef = useRef(false);
  const shouldSyncFocusRef = useRef(true);
  const pendingPopupOpenKeyRef = useRef<string | null>(null);
  const focusAllRetryRafRef = useRef<number | null>(null);
  const visiblePopupRef = useRef<string | null>(null);
  const mapFocusModeRef = useRef<MapFocusMode>("first");
  const popupOpenTimerRef = useRef<number | null>(null);
  const initialViewportAlignedRef = useRef(false);

  const selectedPalette = useMemo(
    () => (isDarkTheme ? MAP_PALETTE_DARK : MAP_PALETTE_LIGHT),
    [isDarkTheme],
  );
  const selectedPaletteDistance = useMemo(
    () =>
      isDarkTheme ? MAP_PALETTE_DARK_DISTANCE : MAP_PALETTE_LIGHT_DISTANCE,
    [isDarkTheme],
  );

  const locationKeys = useMemo(
    () => createStableLocationKeys(locations),
    [locations],
  );

  const keyedLocations = useMemo<KeyedLocation[]>(
    () =>
      locations.map((locationItem, index) => ({
        key: locationKeys[index],
        location: locationItem,
        index,
      })),
    [locationKeys, locations],
  );

  const activePopupEntry = useMemo(
    () => keyedLocations.find((entry) => entry.key === visiblePopupKey) ?? null,
    [keyedLocations, visiblePopupKey],
  );

  const activePopupColor = useMemo(() => {
    if (!activePopupEntry) return "#DC2626";
    return assignedColors[activePopupEntry.index] ?? "#DC2626";
  }, [activePopupEntry, assignedColors]);

  const getFullscreenElement = useCallback((): Element | null => {
    const doc = document as DocumentWithFullscreen;
    return (
      document.fullscreenElement ??
      doc.webkitFullscreenElement ??
      doc.mozFullScreenElement ??
      doc.msFullscreenElement ??
      null
    );
  }, []);

  const syncKioskQueryWithFullscreen = useCallback(
    (fullscreenEnabled: boolean) => {
      const params = new URLSearchParams(window.location.search);
      const hasKioskFlag = params.get("kiosk") === "1";
      if (fullscreenEnabled === hasKioskFlag) return;

      if (fullscreenEnabled) {
        params.set("kiosk", "1");
      } else {
        params.delete("kiosk");
      }

      const nextSearch = params.toString();
      navigate(
        {
          pathname: location.pathname,
          search: nextSearch ? `?${nextSearch}` : "",
        },
        { replace: true },
      );
    },
    [location.pathname, navigate],
  );

  const totalEmployees = useMemo(
    () => locations.reduce((sum, loc) => sum + loc.employees, 0),
    [locations],
  );

  const mapExtentMeters = useMemo(() => {
    if (locations.length < 2) return 0;

    let minLat = Number.POSITIVE_INFINITY;
    let minLng = Number.POSITIVE_INFINITY;
    let maxLat = Number.NEGATIVE_INFINITY;
    let maxLng = Number.NEGATIVE_INFINITY;

    for (const loc of locations) {
      minLat = Math.min(minLat, loc.lat);
      minLng = Math.min(minLng, loc.lng);
      maxLat = Math.max(maxLat, loc.lat);
      maxLng = Math.max(maxLng, loc.lng);
    }

    return calculateDistanceMeters(minLat, minLng, maxLat, maxLng);
  }, [locations]);

  const lastRequestLabel = useMemo(() => {
    if (!lastRequestAt) return "ожидание";
    return new Intl.DateTimeFormat("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(lastRequestAt);
  }, [lastRequestAt]);

  const firstPointButtonLabel = useMemo(
    () =>
      isMapPriorityLayout
        ? "1-я"
        : isKiosk && isPhoneLandscapeViewport && !isFullscreen
        ? "1-я"
        : isPhoneLandscapeViewport || isUltraNarrowViewport
        ? "Первая"
        : "Первая точка",
    [
      isFullscreen,
      isKiosk,
      isMapPriorityLayout,
      isPhoneLandscapeViewport,
      isUltraNarrowViewport,
    ],
  );

  const allPointsButtonLabel = useMemo(
    () =>
      isMapPriorityLayout
        ? "Все"
        : isKiosk && isPhoneLandscapeViewport && !isFullscreen
        ? "Все"
        : isPhoneLandscapeViewport
        ? "Все точки"
        : isUltraNarrowViewport
          ? "Карта"
          : "Полная карта",
    [
      isFullscreen,
      isKiosk,
      isMapPriorityLayout,
      isPhoneLandscapeViewport,
      isUltraNarrowViewport,
    ],
  );

  const zoomControlPosition = useMemo<"topright" | "bottomright">(
    () => {
      if (isPhoneLandscapeViewport) {
        return isKiosk ? "bottomright" : "topright";
      }
      return isMobileViewport ? "topright" : "bottomright";
    },
    [isKiosk, isMobileViewport, isPhoneLandscapeViewport],
  );

  const dispatch = useCallback((action: BaseAction<MapDispatchPayload>) => {
    switch (action.type) {
      case BaseAction.SET_LOADING:
        setLoading(action.payload as boolean);
        break;
      case BaseAction.SET_DATA:
        setLocations(action.payload as LocationData[]);
        setLoading(false);
        break;
      case BaseAction.SET_ERROR:
        setError(action.payload as string);
        setLoading(false);
        break;
      default:
        break;
    }
  }, []);

  const fetchLocations = useCallback(
    async (selectedDate: string, options?: { silent?: boolean }) => {
      if (!options?.silent) {
        dispatch(new BaseAction(BaseAction.SET_LOADING, true));
      }
      setLastRequestAt(new Date());

      try {
        const response = await axiosInstance.get(
          `${apiUrl}/api/locations?employees=true&date_at=${selectedDate}`,
        );
        const fetchedLocations: LocationData[] = response.data.filter(
          (loc: LocationData) => loc.employees > 0,
        );

        dispatch(new BaseAction(BaseAction.SET_DATA, fetchedLocations));

        const fetchedKeys = createStableLocationKeys(fetchedLocations);
        const currentVisiblePopup = visiblePopupRef.current;

        if (currentVisiblePopup && fetchedKeys.includes(currentVisiblePopup)) {
          pendingPopupOpenKeyRef.current = currentVisiblePopup;
          setVisiblePopupKey(currentVisiblePopup);
        } else if (mapFocusModeRef.current === "first" && fetchedKeys[0]) {
          pendingPopupOpenKeyRef.current = fetchedKeys[0];
          setVisiblePopupKey(null);
        } else {
          pendingPopupOpenKeyRef.current = null;
          setVisiblePopupKey(null);
        }

        if (!options?.silent || mapFocusModeRef.current === "first") {
          shouldSyncFocusRef.current = true;
        }

        setIsMarkersVisible(true);
      } catch {
        dispatch(
          new BaseAction(BaseAction.SET_ERROR, "Не удалось загрузить данные."),
        );
      }
    },
    [dispatch],
  );

  useEffect(() => {
    fetchLocations(dateAt);
  }, [dateAt, fetchLocations]);

  useEffect(() => {
    if (reportsAutoRefreshMinutes <= 0) return;
    const intervalMs = reportsAutoRefreshMinutes * 60 * 1000;
    const id = window.setInterval(
      () => fetchLocations(dateAt, { silent: true }),
      intervalMs,
    );
    return () => clearInterval(id);
  }, [dateAt, reportsAutoRefreshMinutes, fetchLocations]);

  const handleDateChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedDate = event.target.value;
    const today = new Date().toISOString().split("T")[0];
    setMapFocusMode("first");
    mapFocusModeRef.current = "first";
    shouldSyncFocusRef.current = true;
    pendingPopupOpenKeyRef.current = null;
    setVisiblePopupKey(null);

    if (selectedDate > today) {
      setDateAt(today);
    } else {
      setDateAt(selectedDate);
    }
  };

  useEffect(() => {
    if (typeof document === "undefined") return undefined;

    const applyTheme = () => {
      setIsDarkTheme(document.documentElement.classList.contains("dark"));
    };
    applyTheme();

    const observer = new MutationObserver(applyTheme);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setAssignedColors(
      assignHighContrastColors(locations, selectedPalette, selectedPaletteDistance),
    );
  }, [locations, selectedPalette, selectedPaletteDistance]);

  useEffect(() => {
    visiblePopupRef.current = visiblePopupKey;
  }, [visiblePopupKey]);

  useEffect(() => {
    mapFocusModeRef.current = mapFocusMode;
  }, [mapFocusMode]);

  const safeInvalidateMapSize = useCallback(() => {
    if (!mapRef.current) return;
    try {
      mapRef.current.invalidateSize({ pan: false, debounceMoveend: true });
    } catch {
      mapRef.current.invalidateSize();
    }
  }, []);

  const safeSetView = useCallback(
    (center: [number, number], zoom: number, animate: boolean): boolean => {
      const map = mapRef.current;
      if (!map) return false;

      const mapInternals = map as LeafletMap & {
        _loaded?: boolean;
        _mapPane?: HTMLElement | null;
      };

      if (!mapInternals._loaded || !mapInternals._mapPane) {
        return false;
      }

      const container = map.getContainer();
      if (!container || !container.isConnected) {
        return false;
      }

      try {
        map.setView(center, zoom, { animate });
        return true;
      } catch {
        try {
          safeInvalidateMapSize();
          map.setView(center, zoom, { animate: false });
          return true;
        } catch {
          return false;
        }
      }
    },
    [safeInvalidateMapSize],
  );

  const safeFitBounds = useCallback(
    (
      bounds: L.LatLngBounds,
      animate: boolean,
      maxZoom: number,
      padding = 72,
    ): boolean => {
      const map = mapRef.current;
      if (!map) return false;

      const mapInternals = map as LeafletMap & {
        _loaded?: boolean;
        _mapPane?: HTMLElement | null;
      };

      if (!mapInternals._loaded || !mapInternals._mapPane) {
        return false;
      }

      const container = map.getContainer();
      if (!container || !container.isConnected) {
        return false;
      }

      try {
        map.fitBounds(bounds, {
          padding: [padding, padding],
          maxZoom,
          animate,
        });
        return true;
      } catch {
        try {
          safeInvalidateMapSize();
          map.fitBounds(bounds, {
            padding: [padding, padding],
            maxZoom,
            animate: false,
          });
          return true;
        } catch {
          return false;
        }
      }
    },
    [safeInvalidateMapSize],
  );

  const getFirstFocusZoom = useCallback(
    (sourceLocations: LocationData[]): number => {
      const baseZoom = isTvLikeDevice
        ? 14.4
        : isPhoneViewportClass
          ? isLandscapeViewport
            ? 14.2
            : 14.5
          : isTablet
            ? isLandscapeViewport
              ? 14.4
              : 14.7
            : isWideViewport
              ? 14.9
              : 14.6;

      if (sourceLocations.length <= 1) {
        return Math.min(MAP_FIRST_FOCUS_MAX_ZOOM, baseZoom + 0.38);
      }

      const [firstLocation, ...restLocations] = sourceLocations;
      const sortedNeighbors = restLocations
        .map((loc) => ({
          location: loc,
          distanceM: calculateDistanceMeters(
            firstLocation.lat,
            firstLocation.lng,
            loc.lat,
            loc.lng,
          ),
        }))
        .sort((a, b) => a.distanceM - b.distanceM);

      const nearLocations = sortedNeighbors.slice(0, 3).map((item) => item.location);
      const focusLocations = [firstLocation, ...nearLocations];

      const map = mapRef.current;
      if (map) {
        const focusBounds = L.latLngBounds(
          focusLocations.map((item) => [item.lat, item.lng] as [number, number]),
        );
        const allBounds = L.latLngBounds(
          sourceLocations.map((item) => [item.lat, item.lng] as [number, number]),
        );

        if (focusBounds.isValid() && allBounds.isValid()) {
          const focusPadding = isMobileViewport ? 44 : isTablet ? 58 : 74;
          const allPadding = isMobileViewport ? 40 : isTablet ? 56 : 68;

          const focusZoom = map.getBoundsZoom(
            focusBounds,
            false,
            L.point(focusPadding, focusPadding),
          );
          const allZoom = map.getBoundsZoom(
            allBounds,
            false,
            L.point(allPadding, allPadding),
          );

          const adjustedZoom = Math.max(focusZoom, allZoom + 0.65);
          return Math.min(
            MAP_FIRST_FOCUS_MAX_ZOOM,
            Math.max(MAP_FIRST_FOCUS_MIN_ZOOM, adjustedZoom),
          );
        }
      }

      const nearestDistanceM = sortedNeighbors[0]?.distanceM ?? 500;
      const zoomShift =
        nearestDistanceM <= 90
          ? 1.4
          : nearestDistanceM <= 170
            ? 1.1
            : nearestDistanceM <= 280
              ? 0.82
              : nearestDistanceM <= 480
                ? 0.56
                : nearestDistanceM <= 860
                  ? 0.25
                  : -0.12;

      return Math.min(
        MAP_FIRST_FOCUS_MAX_ZOOM,
        Math.max(MAP_FIRST_FOCUS_MIN_ZOOM, baseZoom + zoomShift),
      );
    },
    [
      isLandscapeViewport,
      isMobileViewport,
      isPhoneViewportClass,
      isTablet,
      isTvLikeDevice,
      isWideViewport,
    ],
  );

  const centerMapOnFirstLocation = useCallback(
    (animate = false, targetEntries?: KeyedLocation[]): boolean => {
      const sourceEntries = targetEntries ?? keyedLocations;
      if (sourceEntries.length === 0) {
        return safeSetView(MAP_DEFAULT_CENTER, MAP_DEFAULT_ZOOM, false);
      }

      const [firstEntry] = sourceEntries;
      const sourceLocations = sourceEntries.map((entry) => entry.location);
      const targetZoom = getFirstFocusZoom(sourceLocations);
      return safeSetView(
        [firstEntry.location.lat, firstEntry.location.lng],
        targetZoom,
        animate,
      );
    },
    [getFirstFocusZoom, keyedLocations, safeSetView],
  );

  const fitMapToAllLocations = useCallback(
    (animate = true, targetEntries?: KeyedLocation[]): boolean => {
      const sourceEntries = targetEntries ?? keyedLocations;
      if (sourceEntries.length === 0) {
        return safeSetView(MAP_DEFAULT_CENTER, MAP_DEFAULT_ZOOM, false);
      }

      if (sourceEntries.length === 1) {
        return centerMapOnFirstLocation(animate, sourceEntries);
      }

      const bounds = L.latLngBounds(
        sourceEntries.map((entry) =>
          [entry.location.lat, entry.location.lng] as [number, number],
        ),
      );
      if (!bounds.isValid()) return false;

      const fitPadding = isMobileViewport ? 42 : isTablet ? 60 : 84;
      return safeFitBounds(bounds, animate, MAP_MULTI_POINT_ZOOM, fitPadding);
    },
    [
      centerMapOnFirstLocation,
      isMobileViewport,
      isTablet,
      keyedLocations,
      safeFitBounds,
      safeSetView,
    ],
  );

  const syncMapFocusMode = useCallback(
    (
      animate = false,
      targetMode?: MapFocusMode,
      targetEntries?: KeyedLocation[],
    ): boolean => {
      const nextMode = targetMode ?? mapFocusModeRef.current;
      if (nextMode === "all") {
        return fitMapToAllLocations(animate, targetEntries);
      }
      return centerMapOnFirstLocation(animate, targetEntries);
    },
    [centerMapOnFirstLocation, fitMapToAllLocations],
  );

  const schedulePopupOpenAfterMove = useCallback((targetKey: string | null) => {
    if (popupOpenTimerRef.current !== null) {
      window.clearTimeout(popupOpenTimerRef.current);
      popupOpenTimerRef.current = null;
    }

    if (!targetKey) {
      setVisiblePopupKey(null);
      return;
    }

    const map = mapRef.current;
    if (!map) {
      setVisiblePopupKey(targetKey);
      return;
    }

    let isDone = false;

    const finalize = () => {
      if (isDone) return;
      isDone = true;
      map.off("moveend", finalize);
      map.off("zoomend", finalize);
      setVisiblePopupKey(targetKey);
      if (popupOpenTimerRef.current !== null) {
        window.clearTimeout(popupOpenTimerRef.current);
        popupOpenTimerRef.current = null;
      }
    };

    map.once("moveend", finalize);
    map.once("zoomend", finalize);
    popupOpenTimerRef.current = window.setTimeout(finalize, 260);
  }, []);

  const handleFocusFirst = useCallback(() => {
    if (focusAllRetryRafRef.current !== null) {
      window.cancelAnimationFrame(focusAllRetryRafRef.current);
      focusAllRetryRafRef.current = null;
    }

    setMapFocusMode("first");
    mapFocusModeRef.current = "first";
    shouldSyncFocusRef.current = false;

    const firstEntry = keyedLocations[0];
    if (!firstEntry) {
      pendingPopupOpenKeyRef.current = null;
      setVisiblePopupKey(null);
      centerMapOnFirstLocation(true, keyedLocations);
      return;
    }

    pendingPopupOpenKeyRef.current = firstEntry.key;
    setVisiblePopupKey(null);

    const centered = centerMapOnFirstLocation(true, keyedLocations);
    if (centered) {
      schedulePopupOpenAfterMove(firstEntry.key);
    } else {
      shouldSyncFocusRef.current = true;
    }
  }, [centerMapOnFirstLocation, keyedLocations, schedulePopupOpenAfterMove]);

  const handleFocusAll = useCallback(() => {
    if (focusAllRetryRafRef.current !== null) {
      window.cancelAnimationFrame(focusAllRetryRafRef.current);
      focusAllRetryRafRef.current = null;
    }

    setMapFocusMode("all");
    mapFocusModeRef.current = "all";
    shouldSyncFocusRef.current = false;
    pendingPopupOpenKeyRef.current = null;
    setVisiblePopupKey(null);

    if (mapRef.current) {
      try {
        mapRef.current.stop();
      } catch {
        // ignore map stop failures
      }
    }

    const fitted = fitMapToAllLocations(true, keyedLocations);

    if (!fitted) {
      focusAllRetryRafRef.current = window.requestAnimationFrame(() => {
        focusAllRetryRafRef.current = null;
        const retryFitted = fitMapToAllLocations(false, keyedLocations);
        if (!retryFitted) {
          shouldSyncFocusRef.current = true;
        }
      });
    }
  }, [fitMapToAllLocations, keyedLocations]);

  const handleMarkerClick = useCallback(
    (entry: KeyedLocation) => {
      setVisiblePopupKey((currentVisible) => {
        const nextVisible = currentVisible === entry.key ? null : entry.key;

        if (nextVisible) {
          const currentZoom = mapRef.current?.getZoom() ?? mapZoom;
          safeSetView(
            [entry.location.lat, entry.location.lng],
            currentZoom,
            true,
          );
        }

        return nextVisible;
      });
    },
    [mapZoom, safeSetView],
  );

  const getMobileDockHeight = useCallback((): number => {
    if (typeof document === "undefined") return MOBILE_DOCK_FALLBACK_HEIGHT;
    const dock = document.querySelector(MOBILE_DOCK_QUERY) as HTMLElement | null;
    if (!dock) return MOBILE_DOCK_FALLBACK_HEIGHT;
    const dockHeight = Math.round(dock.getBoundingClientRect().height);
    return Math.max(MOBILE_DOCK_FALLBACK_HEIGHT, dockHeight);
  }, []);

  const handleMapReady = useCallback(() => {
    setMapReadyVersion((prev) => prev + 1);
  }, []);

  const updateMapViewportHeight = useCallback(() => {
    const mapViewportNode = mapViewportRef.current;
    if (!mapViewportNode) return;

    const visualViewportHeight =
      window.visualViewport?.height ??
      window.innerHeight ??
      document.documentElement.clientHeight;
    const mapTop = mapViewportNode.getBoundingClientRect().top;
    const dockHeight = getMobileDockHeight();
    const safeBottomInset =
      window.visualViewport && window.innerHeight
        ? Math.max(0, window.innerHeight - window.visualViewport.height)
        : 0;

    let bottomReserve = 14;
    if (!isFullscreen && isKiosk && isMobileViewport) {
      bottomReserve = isPhoneLandscapeViewport
        ? 6 + safeBottomInset
        : 10 + safeBottomInset;
    } else if (!isFullscreen && !isKiosk && isMobileViewport) {
      bottomReserve = isPhoneLandscapeViewport
        ? dockHeight + 8 + safeBottomInset
        : isLandscapeViewport
          ? dockHeight + 16 + safeBottomInset
          : dockHeight + 20 + safeBottomInset;
    } else if (!isFullscreen && !isKiosk) {
      bottomReserve = isTvLikeDevice ? 28 : 52;
    } else if (isFullscreen && isMobileViewport) {
      bottomReserve = 8;
    }

    const minHeight = isTvLikeDevice
      ? isLandscapeViewport
        ? 460
        : 400
      : isPhoneViewportClass
        ? isLandscapeViewport
          ? 244
          : 336
        : isTablet
          ? 340
          : 420;
    const maxHeight = isTvLikeDevice ? 1220 : isWideViewport ? 1100 : 960;

    const nextHeight = Math.round(
      Math.max(
        minHeight,
        Math.min(maxHeight, visualViewportHeight - mapTop - bottomReserve),
      ),
    );

    setMapViewportHeight((prev) => {
      if (Math.abs(prev - nextHeight) < 2) return prev;
      return nextHeight;
    });
  }, [
    getMobileDockHeight,
    isFullscreen,
    isKiosk,
    isLandscapeViewport,
    isMobileViewport,
    isPhoneLandscapeViewport,
    isPhoneViewportClass,
    isTablet,
    isTvLikeDevice,
    isWideViewport,
  ]);

  useEffect(() => {
    if (loading || isFullscreen || !isMobileViewport) return;
    if (initialViewportAlignedRef.current) return;

    const targetNode = isPhoneLandscapeViewport
      ? mapViewportRef.current
      : controlsRef.current;
    if (!targetNode) return;

    initialViewportAlignedRef.current = true;
    const id = window.setTimeout(() => {
      const targetTop = Math.max(
        0,
        Math.round(targetNode.getBoundingClientRect().top + window.scrollY - 4),
      );
      window.scrollTo({ top: targetTop, behavior: "auto" });
    }, 60);

    return () => window.clearTimeout(id);
  }, [
    isFullscreen,
    isMobileViewport,
    isPhoneLandscapeViewport,
    loading,
  ]);

  useEffect(() => {
    initialViewportAlignedRef.current = false;
  }, [location.search, location.pathname]);

  const handleFullscreenToggle = useCallback(async () => {
    if (fullscreenToggleLockRef.current) return;

    const docEl = document.documentElement as DocumentElementWithFullscreen;
    const doc = document as DocumentWithFullscreen;
    const currentlyFullscreen = !!getFullscreenElement();

    fullscreenToggleLockRef.current = true;
    setIsFullscreenBusy(true);

    try {
      if (!currentlyFullscreen) {
        const req =
          docEl.requestFullscreen ??
          docEl.webkitRequestFullscreen ??
          docEl.mozRequestFullScreen ??
          docEl.msRequestFullscreen;

        if (req) {
          await Promise.resolve(req.call(docEl));
        }
      } else {
        const exit =
          document.exitFullscreen ??
          doc.webkitExitFullscreen ??
          doc.mozCancelFullScreen ??
          doc.msExitFullscreen;

        if (exit) {
          await Promise.resolve(exit.call(doc));
        }
      }
    } catch {
      // ignore fullscreen errors
    } finally {
      window.setTimeout(() => {
        if (!getFullscreenElement()) {
          setIsFullscreenBusy(false);
          fullscreenToggleLockRef.current = false;
        }
      }, 350);
    }
  }, [getFullscreenElement]);

  const handleFullscreenChange = useCallback(() => {
    const newFullscreenState = !!getFullscreenElement();
    setIsFullscreen(newFullscreenState);
    setIsFullscreenBusy(false);
    fullscreenToggleLockRef.current = false;
    syncKioskQueryWithFullscreen(newFullscreenState);

    window.setTimeout(() => {
      updateMapViewportHeight();
      safeInvalidateMapSize();

      if (shouldSyncFocusRef.current) {
        const synced = syncMapFocusMode(false, mapFocusModeRef.current, keyedLocations);
        if (synced) {
          shouldSyncFocusRef.current = false;
          if (mapFocusModeRef.current === "first") {
            const keyToOpen = pendingPopupOpenKeyRef.current ?? keyedLocations[0]?.key;
            schedulePopupOpenAfterMove(keyToOpen ?? null);
          }
        }
      }
    }, 480);
  }, [
    getFullscreenElement,
    keyedLocations,
    safeInvalidateMapSize,
    schedulePopupOpenAfterMove,
    syncKioskQueryWithFullscreen,
    syncMapFocusMode,
    updateMapViewportHeight,
  ]);

  useFullscreenChange(handleFullscreenChange);

  useEffect(() => {
    if (fullscreenToggleLockRef.current) return;
    const fullscreenNow = !!getFullscreenElement();
    setIsFullscreen(fullscreenNow);
    syncKioskQueryWithFullscreen(fullscreenNow);
  }, [getFullscreenElement, location.search, syncKioskQueryWithFullscreen]);

  useEffect(() => {
    if (!shouldSyncFocusRef.current) return;

    let attempts = 0;

    const trySyncFocus = () => {
      const synced = syncMapFocusMode(false, mapFocusModeRef.current, keyedLocations);
      if (!synced) return false;

      shouldSyncFocusRef.current = false;

      if (mapFocusModeRef.current === "first") {
        const targetKey = pendingPopupOpenKeyRef.current ?? keyedLocations[0]?.key;
        schedulePopupOpenAfterMove(targetKey ?? null);
      } else {
        setVisiblePopupKey(null);
      }

      pendingPopupOpenKeyRef.current = null;
      return true;
    };

    if (trySyncFocus()) {
      return;
    }

    const id = window.setInterval(() => {
      attempts += 1;
      if (trySyncFocus() || attempts >= MAP_RETRY_SYNC_ATTEMPTS) {
        window.clearInterval(id);
      }
    }, MAP_RETRY_SYNC_INTERVAL_MS);

    return () => window.clearInterval(id);
  }, [keyedLocations, mapReadyVersion, schedulePopupOpenAfterMove, syncMapFocusMode]);

  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.visibilityState !== "visible") return;
      window.setTimeout(() => {
        updateMapViewportHeight();
        safeInvalidateMapSize();

        if (shouldSyncFocusRef.current) {
          const synced = syncMapFocusMode(false, mapFocusModeRef.current, keyedLocations);
          if (synced) {
            shouldSyncFocusRef.current = false;
            if (mapFocusModeRef.current === "first") {
              const targetKey = pendingPopupOpenKeyRef.current ?? keyedLocations[0]?.key;
              schedulePopupOpenAfterMove(targetKey ?? null);
            }
          }
        }
      }, 90);
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [
    keyedLocations,
    safeInvalidateMapSize,
    schedulePopupOpenAfterMove,
    syncMapFocusMode,
    updateMapViewportHeight,
  ]);

  useEffect(() => {
    updateMapViewportHeight();

    const handleViewportMutation = () => {
      updateMapViewportHeight();
      safeInvalidateMapSize();
    };

    window.addEventListener("resize", handleViewportMutation);
    window.addEventListener("orientationchange", handleViewportMutation);
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", handleViewportMutation);
      window.visualViewport.addEventListener("scroll", handleViewportMutation);
    }

    document.addEventListener("fullscreenchange", handleViewportMutation);
    document.addEventListener("webkitfullscreenchange", handleViewportMutation);

    const observedNodes = [
      mapViewportRef.current,
      controlsRef.current,
      mapContainerRef.current,
    ].filter((node): node is HTMLDivElement => node !== null);

    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined" && observedNodes.length > 0) {
      resizeObserver = new ResizeObserver(() => {
        updateMapViewportHeight();
      });
      observedNodes.forEach((node) => resizeObserver?.observe(node));
    }

    return () => {
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
      window.removeEventListener("resize", handleViewportMutation);
      window.removeEventListener("orientationchange", handleViewportMutation);
      if (window.visualViewport) {
        window.visualViewport.removeEventListener("resize", handleViewportMutation);
        window.visualViewport.removeEventListener("scroll", handleViewportMutation);
      }
      document.removeEventListener("fullscreenchange", handleViewportMutation);
      document.removeEventListener("webkitfullscreenchange", handleViewportMutation);
    };
  }, [mapReadyVersion, safeInvalidateMapSize, updateMapViewportHeight]);

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      safeInvalidateMapSize();
    }, 130);
    return () => window.clearTimeout(timerId);
  }, [mapViewportHeight, safeInvalidateMapSize]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "F11") {
        event.preventDefault();
        handleFullscreenToggle();
      }
    };

    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [handleFullscreenToggle]);

  useEffect(() => {
    return () => {
      if (focusAllRetryRafRef.current !== null) {
        window.cancelAnimationFrame(focusAllRetryRafRef.current);
      }
      if (popupOpenTimerRef.current !== null) {
        window.clearTimeout(popupOpenTimerRef.current);
      }
      initialViewportAlignedRef.current = false;
      window.scrollTo(0, 0);
    };
  }, []);

  const handleMapBackgroundClick = useCallback(() => {
    setVisiblePopupKey(null);
  }, []);

  const isKioskLandscapePhone = isKiosk && isPhoneLandscapeViewport && !isFullscreen;
  const isPhoneLandscapeCompact = isPhoneLandscapeViewport && !isFullscreen;
  const isPackedHeaderViewport =
    !isMapPriorityLayout &&
    !isKioskLandscapePhone &&
    isLandscapeViewport &&
    viewport.height <= 620 &&
    (isFullscreen || isKiosk || isDenseHeaderViewport);
  const shouldInlineSummaryChips = isPackedHeaderViewport;
  const showHeaderTitleBlock = !isPhoneLandscapeCompact && !isMapPriorityLayout;
  const showHeaderMetaRow = !isKioskLandscapePhone && !isMapPriorityLayout;

  const topContainerClass = isFullscreen
    ? isPackedHeaderViewport
      ? "px-2 sm:px-3 pt-1 pb-1"
      : "px-2 sm:px-3 pt-2 pb-2"
    : isMapPriorityLayout
      ? "px-1.5 pt-0 pb-0"
    : isKioskLandscapePhone
      ? "px-1.5 pt-0.5 pb-0"
    : isPhoneLandscapeCompact
      ? "px-2 pt-0.5 pb-0.5"
    : isKioskMobileViewport
      ? isDenseHeaderViewport
        ? "px-2 pt-1 pb-0.5"
        : "px-2.5 pt-1.5 pb-1"
    : isKiosk
      ? isDenseHeaderViewport
        ? "px-2.5 sm:px-4 pt-2 sm:pt-3 pb-1.5"
        : "px-2.5 sm:px-4 pt-3 sm:pt-4 pb-2"
      : isDenseHeaderViewport
        ? "px-2.5 sm:px-4 pt-2 sm:pt-3 pb-1.5"
        : "px-3 sm:px-4 pt-3 sm:pt-5 pb-2 sm:pb-3";

  const controlsFrameClass = isKioskLandscapePhone
    ? "rounded-md shadow-sm"
    : isMapPriorityLayout
      ? "rounded-md shadow-sm"
    : isPhoneLandscapeCompact
      ? "rounded-lg shadow-md"
      : "rounded-2xl";

  const panelPaddingClass = isPhoneLandscapeCompact
    ? isKioskLandscapePhone
      ? "px-1.5 py-0.5 gap-0.5"
      : "px-2 py-1 gap-1"
    : isMapPriorityLayout
    ? "px-1.5 py-0.5 gap-0.5"
    : isPackedHeaderViewport
    ? "px-2.5 sm:px-3 py-1.5 gap-1.5"
    : isKioskMobileViewport
    ? isDenseHeaderViewport
      ? "px-2 py-1.5 gap-1.5"
      : "px-2.5 py-2 gap-2"
    : isDenseHeaderViewport
    ? "px-2.5 sm:px-3 py-2 sm:py-2.5 gap-2"
    : "px-3 sm:px-4 py-2.5 sm:py-3 gap-3";

  const summaryTextClass = isPhoneLandscapeCompact
    ? "text-[9px]"
    : isDenseHeaderViewport
    ? "text-[10px]"
    : "text-[11px] sm:text-xs";

  const summaryChipClass = isPhoneLandscapeCompact
    ? "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5"
    : isDenseHeaderViewport
    ? "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5"
    : "inline-flex items-center gap-1 rounded-full border px-2 py-0.5";

  const metaChipClass = isPhoneLandscapeCompact
    ? "inline-flex h-6 items-center gap-1 rounded-md border border-white/50 dark:border-slate-700/80 bg-white/55 dark:bg-slate-900/55 px-1.5 text-[9px] text-gray-700 dark:text-gray-300"
    : isMapPriorityLayout
    ? "inline-flex h-6 items-center gap-1 rounded-md border border-white/50 dark:border-slate-700/80 bg-white/55 dark:bg-slate-900/55 px-1.5 text-[9px] text-gray-700 dark:text-gray-300"
    : isPackedHeaderViewport
    ? "inline-flex h-7 items-center gap-1 rounded-md border border-white/50 dark:border-slate-700/80 bg-white/55 dark:bg-slate-900/55 px-2 text-[10px] text-gray-700 dark:text-gray-300"
    : isDenseHeaderViewport
    ? "inline-flex h-8 items-center gap-1 rounded-lg border border-white/50 dark:border-slate-700/80 bg-white/55 dark:bg-slate-900/55 px-2 text-[10px] text-gray-700 dark:text-gray-300"
    : "inline-flex h-10 items-center gap-1.5 rounded-lg border border-white/50 dark:border-slate-700/80 bg-white/55 dark:bg-slate-900/55 px-3 text-[11px] sm:text-xs text-gray-700 dark:text-gray-300";

  const actionButtonClass = isPhoneLandscapeCompact
    ? isKioskLandscapePhone
      ? "inline-flex h-6 items-center justify-center gap-1 px-1 rounded-md text-[9px] font-semibold border transition-colors"
      : "inline-flex h-7 items-center justify-center gap-1 px-1.5 rounded-md text-[9px] font-semibold border transition-colors"
    : isMapPriorityLayout
    ? "inline-flex h-7 items-center justify-center gap-1 px-1.5 rounded-md text-[10px] font-semibold border transition-colors"
    : isPackedHeaderViewport
    ? "inline-flex h-8 items-center justify-center gap-1.5 px-2.5 rounded-lg text-[11px] font-semibold border transition-colors"
    : isDenseHeaderViewport
    ? "inline-flex h-9 items-center justify-center gap-1.5 px-2.5 rounded-lg text-[11px] font-semibold border transition-colors"
    : "inline-flex h-10 items-center justify-center gap-2 px-3.5 rounded-lg text-xs sm:text-sm font-semibold border transition-colors";

  const buttonIconClass = isKioskLandscapePhone
    ? "w-3 h-3"
    : isMapPriorityLayout
      ? "w-3 h-3"
    : isDenseHeaderViewport
      ? "w-3.5 h-3.5"
      : "w-4 h-4";

  const fullscreenButtonLabel = isFullscreenBusy
    ? isFullscreen
      ? "Выход..."
      : "Открытие..."
    : isFullscreen
      ? "Выход"
      : isPhoneLandscapeCompact
        ? "Экран"
        : "Полный экран";

  const pageContainerStyle = useMemo<React.CSSProperties | undefined>(() => {
    if (!isMobileViewport || isFullscreen) return undefined;

    if (isKiosk) {
      return {
        paddingTop: isPhoneLandscapeViewport
          ? isKioskLandscapePhone
            ? "max(0.1rem, env(safe-area-inset-top, 0px))"
            : "max(0.25rem, env(safe-area-inset-top, 0px))"
          : "max(0.45rem, env(safe-area-inset-top, 0px))",
        paddingBottom: isPhoneLandscapeViewport
          ? isKioskLandscapePhone
            ? "max(0.1rem, env(safe-area-inset-bottom, 0px))"
            : "max(0.25rem, env(safe-area-inset-bottom, 0px))"
          : "max(0.5rem, env(safe-area-inset-bottom, 0px))",
      };
    }

    return {
      paddingBottom: isPhoneLandscapeViewport
        ? "calc(0.35rem + env(safe-area-inset-bottom, 0px))"
        : "calc(0.75rem + env(safe-area-inset-bottom, 0px))",
    };
  }, [
    isFullscreen,
    isKiosk,
    isKioskLandscapePhone,
    isMobileViewport,
    isPhoneLandscapeViewport,
  ]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <LoaderComponent />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Notification message={error} type="error" link="/" />
      </div>
    );
  }

  return (
    <motion.div
      className="relative min-h-screen overflow-hidden"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      style={pageContainerStyle}
    >
      <div className={`relative z-20 mx-auto w-full max-w-[1600px] ${topContainerClass}`}>
        <motion.div
          ref={controlsRef}
          className={`border shadow-lg backdrop-blur-md flex flex-col ${panelPaddingClass} ${
            isFullscreen
              ? "border-white/55 dark:border-slate-700/70 bg-white/65 dark:bg-slate-900/45"
              : "border-white/65 dark:border-slate-700/80 bg-white/70 dark:bg-slate-900/55"
          } ${controlsFrameClass}`}
          variants={dateVariants}
          initial="hidden"
          animate="visible"
        >
          <div
            className={`flex flex-col ${
              isPackedHeaderViewport
                ? "gap-1.5 md:flex-row md:items-start md:justify-between"
                : isDenseHeaderViewport
                ? "gap-2"
                : "gap-3 xl:flex-row xl:items-center xl:justify-between"
            }`}
          >
            {showHeaderTitleBlock && (
              <div className="min-w-0">
                <h1
                  className={`font-semibold text-gray-800 dark:text-gray-100 truncate ${
                    isPackedHeaderViewport
                      ? "text-base sm:text-lg"
                      : isDenseHeaderViewport
                        ? "text-base"
                        : "text-lg sm:text-xl"
                  }`}
                >
                  {isDenseHeaderViewport ? "Карта" : "Карта посещаемости"}
                </h1>
                {!shouldInlineSummaryChips && (
                  <div
                    className={`mt-1 flex flex-wrap items-center gap-1.5 sm:gap-2 ${summaryTextClass}`}
                  >
                    <span
                      className={`${summaryChipClass} border-sky-200/90 dark:border-sky-700/70 bg-sky-50/90 dark:bg-sky-900/30 text-sky-700 dark:text-sky-200`}
                    >
                      <FiMapPin className="w-3 h-3" />
                      {NUMBER_FORMATTER.format(locations.length)} точек
                    </span>
                    <span
                      className={`${summaryChipClass} border-violet-200/90 dark:border-violet-700/70 bg-violet-50/90 dark:bg-violet-900/30 text-violet-700 dark:text-violet-200`}
                    >
                      <FiUsers className="w-3 h-3" />
                      {NUMBER_FORMATTER.format(totalEmployees)} посещений
                    </span>
                  </div>
                )}
              </div>
            )}

            <div
              className={`flex flex-col w-full ${
                isKioskLandscapePhone || isMapPriorityLayout
                  ? "gap-0.5"
                  : isDenseHeaderViewport
                    ? "gap-1.5"
                    : "gap-2 xl:w-auto xl:items-end"
              }`}
            >
              {showHeaderMetaRow && (
                <div
                  className={`flex flex-wrap items-center ${
                    isPhoneLandscapeCompact
                      ? "gap-1 justify-between"
                      : isDenseHeaderViewport
                        ? "gap-1.5"
                        : "gap-2 sm:gap-3"
                  }`}
                >
                  {shouldInlineSummaryChips && (
                    <>
                      <span
                        className={`${summaryChipClass} border-sky-200/90 dark:border-sky-700/70 bg-sky-50/90 dark:bg-sky-900/30 text-sky-700 dark:text-sky-200`}
                      >
                        <FiMapPin className="w-3 h-3" />
                        {NUMBER_FORMATTER.format(locations.length)} точек
                      </span>
                      <span
                        className={`${summaryChipClass} border-violet-200/90 dark:border-violet-700/70 bg-violet-50/90 dark:bg-violet-900/30 text-violet-700 dark:text-violet-200`}
                      >
                        <FiUsers className="w-3 h-3" />
                        {NUMBER_FORMATTER.format(totalEmployees)} посещений
                      </span>
                    </>
                  )}
                  {!isPhoneLandscapeCompact && (
                    <div className={metaChipClass}>
                      <FiClock className="w-3.5 h-3.5 text-primary-600 dark:text-primary-400" />
                      Запрос: {lastRequestLabel}
                    </div>
                  )}

                  <div className={metaChipClass}>
                    <FaCalendarAlt className="text-primary-600 dark:text-primary-400" />
                    <span className="text-gray-500 dark:text-gray-400">Дата:</span>
                    <EditableDateField
                      value={dateAt}
                      onChange={handleDateChange}
                      containerClassName="m-0 p-0 inline-flex items-center"
                      displayClassName="font-semibold text-gray-800 dark:text-gray-200 hover:text-primary-600 dark:hover:text-primary-400 cursor-pointer leading-none"
                      inputClassName={`border border-gray-300 rounded-md px-2 text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                        isPhoneLandscapeCompact
                          ? "h-6 text-[9px]"
                          : isDenseHeaderViewport
                            ? "h-7 text-xs"
                            : "h-8 text-sm"
                      }`}
                    />
                  </div>
                </div>
              )}

              {isMapPriorityLayout && (
                <div className="flex items-center justify-end">
                  <div className="map-priority-date-chip">
                    <span className="map-priority-date-chip__time-block">
                      <FiClock className="map-priority-date-chip__icon" />
                      <span className="map-priority-date-chip__time">
                        {lastRequestLabel}
                      </span>
                    </span>
                    <span className="map-priority-date-chip__sep" aria-hidden>
                      |
                    </span>
                    <span className="map-priority-date-chip__date-block">
                      <FaCalendarAlt className="map-priority-date-chip__icon" />
                      <EditableDateField
                        value={dateAt}
                        onChange={handleDateChange}
                        containerClassName="map-priority-date-chip__date-wrap"
                        displayClassName="map-priority-date-chip__date"
                        inputClassName="map-priority-date-chip__input"
                      />
                    </span>
                  </div>
                </div>
              )}

              <div
                className={
                  isKioskLandscapePhone
                    ? "grid w-full grid-cols-3 gap-0.5"
                    : isMapPriorityLayout
                      ? "grid w-full grid-cols-3 gap-0.5"
                    : isPhoneLandscapeViewport
                      ? "grid w-full grid-cols-3 gap-1"
                    : `grid w-full gap-2 ${
                        isUltraNarrowViewport ? "grid-cols-1" : "grid-cols-2"
                      } sm:flex sm:w-auto sm:flex-wrap sm:justify-end`
                }
              >
                <motion.button
                  onClick={handleFocusFirst}
                  title="Перейти к первой точке и открыть popup"
                  aria-label="Перейти к первой точке и открыть popup"
                  className={`${actionButtonClass} ${
                    mapFocusMode === "first"
                      ? "border-primary-500 bg-primary-600 text-white shadow-md shadow-primary-700/30"
                      : "border-slate-300 dark:border-slate-600 bg-white/75 dark:bg-slate-900/70 text-slate-700 dark:text-slate-200 hover:bg-white dark:hover:bg-slate-800"
                  }`}
                  variants={buttonVariants}
                  initial="initial"
                  whileHover="hover"
                  whileTap="tap"
                >
                  <FiCrosshair className={buttonIconClass} />
                  {firstPointButtonLabel}
                </motion.button>

                <motion.button
                  onClick={handleFocusAll}
                  title="Показать все точки на карте"
                  aria-label="Показать все точки на карте"
                  className={`${actionButtonClass} ${
                    mapFocusMode === "all"
                      ? "border-primary-500 bg-primary-600 text-white shadow-md shadow-primary-700/30"
                      : "border-slate-300 dark:border-slate-600 bg-white/75 dark:bg-slate-900/70 text-slate-700 dark:text-slate-200 hover:bg-white dark:hover:bg-slate-800"
                  }`}
                  variants={buttonVariants}
                  initial="initial"
                  whileHover="hover"
                  whileTap="tap"
                >
                  <FiMaximize2 className={buttonIconClass} />
                  {allPointsButtonLabel}
                </motion.button>

                <motion.button
                  onClick={handleFullscreenToggle}
                  disabled={isFullscreenBusy}
                  className={`${actionButtonClass} text-white ${
                    isFullscreenBusy
                      ? "bg-primary-400 cursor-not-allowed"
                      : "bg-primary-600 hover:bg-primary-700"
                  } ${
                    isUltraNarrowViewport || isPhoneLandscapeViewport
                      ? ""
                      : "sm:min-w-[152px]"
                  }`}
                  aria-label={
                    isFullscreen
                      ? "Выйти из полноэкранного режима"
                      : "Полноэкранный режим"
                  }
                  variants={buttonVariants}
                  initial="initial"
                  whileHover="hover"
                  whileTap="tap"
                >
                  {isFullscreen && !isFullscreenBusy ? (
                    <FaCompress className={buttonIconClass} />
                  ) : (
                    <FaExpand className={buttonIconClass} />
                  )}
                  <span>{fullscreenButtonLabel}</span>
                </motion.button>
              </div>
            </div>
          </div>
        </motion.div>
      </div>

      <div
        ref={mapViewportRef}
        className={`relative z-10 mx-auto w-full ${
          isFullscreen
            ? "max-w-none px-2 sm:px-3 pb-2 sm:pb-3"
            : isMapPriorityLayout
              ? "max-w-[1600px] px-1.5 pb-0"
            : isKioskLandscapePhone
              ? "max-w-[1600px] px-1.5 pb-0"
            : isPhoneLandscapeCompact
              ? "max-w-[1600px] px-2 pb-0.5"
            : isKioskMobileViewport
              ? isDenseHeaderViewport
                ? "max-w-[1600px] px-2 pb-0.5"
                : "max-w-[1600px] px-2.5 pb-1"
            : isDenseHeaderViewport
              ? "max-w-[1600px] px-2.5 sm:px-4 pb-1.5 sm:pb-3"
              : "max-w-[1600px] px-3 sm:px-4 pb-2 sm:pb-4"
        } transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]`}
        style={{ height: `${mapViewportHeight}px` }}
      >
        <motion.div
          ref={mapContainerRef}
          variants={mapContainerVariants}
          initial="hidden"
          animate="visible"
          className="relative w-full h-full"
        >
          <div
            className={`map-dashboard-surface relative w-full h-full overflow-hidden transition-all duration-500 ${
              isFullscreen
                ? "rounded-2xl border border-white/45 dark:border-slate-700/70 shadow-[0_20px_60px_-25px_rgba(15,23,42,0.75)]"
                : "rounded-2xl border border-white/60 dark:border-slate-700/80 shadow-2xl"
            }`}
          >
            {locations.length === 0 && (
              <div className="pointer-events-none absolute inset-0 z-[650] flex items-center justify-center p-4">
                <motion.div
                  initial={{ opacity: 0, scale: 0.96 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="pointer-events-auto rounded-2xl border border-white/70 dark:border-slate-700/80 bg-white/85 dark:bg-slate-900/85 px-5 py-4 shadow-2xl backdrop-blur-sm text-center max-w-md"
                >
                  <div className="text-base font-semibold text-gray-900 dark:text-gray-100">
                    На выбранную дату нет активных точек
                  </div>
                  <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                    Измени дату или дождись следующего обновления.
                  </div>
                </motion.div>
              </div>
            )}

            {isMapPriorityLayout && (
              <div className="map-priority-chip-row pointer-events-none absolute left-2 top-2 z-[640]">
                <span className="map-priority-chip map-priority-chip--points">
                  <FiMapPin className="map-priority-chip__icon" />
                  <span className="map-priority-chip__value">
                    {NUMBER_FORMATTER.format(locations.length)}
                  </span>
                </span>
                <span className="map-priority-chip map-priority-chip--visits">
                  <FiUsers className="map-priority-chip__icon" />
                  <span className="map-priority-chip__value">
                    {NUMBER_FORMATTER.format(totalEmployees)}
                  </span>
                </span>
              </div>
            )}

            <MapContainer
              center={MAP_DEFAULT_CENTER}
              zoom={MAP_DEFAULT_ZOOM}
              style={{ width: "100%", height: "100%" }}
              zoomControl={false}
              attributionControl={false}
              className="z-10 map-dashboard-map"
            >
              <ZoomControl position={zoomControlPosition} />

              <MapEventHandler
                mapRef={mapRef}
                onMapReady={handleMapReady}
                onMapBackgroundClick={handleMapBackgroundClick}
                onMapViewportChange={setMapZoom}
              />

              <TileLayer
                key="osm-standard"
                url={OSM_TILE_URL}
              />

              {keyedLocations.map((entry) => (
                <AnimatedMarker
                  key={entry.key}
                  position={[entry.location.lat, entry.location.lng]}
                  name={entry.location.name}
                  address={entry.location.address}
                  employees={entry.location.employees}
                  isVisible={isMarkersVisible}
                  onClick={() => handleMarkerClick(entry)}
                  isActive={visiblePopupKey === entry.key}
                  radius={MAP_COLOR_BASE_RADIUS_METERS}
                  color={assignedColors[entry.index] ?? "#DC2626"}
                  mapZoom={mapZoom}
                  mapExtentMeters={mapExtentMeters}
                  isDarkTheme={isDarkTheme}
                />
              ))}
            </MapContainer>

            <AdaptiveLocationPopup
              map={mapRef.current}
              location={activePopupEntry?.location ?? null}
              locations={locations}
              color={activePopupColor}
              isDarkTheme={isDarkTheme}
              isKioskMode={isKiosk || isFullscreen}
              isLandscape={isLandscapeViewport}
              mapZoom={mapZoom}
              viewportWidth={viewport.width}
              viewportHeight={viewport.height}
              onClose={() => setVisiblePopupKey(null)}
            />
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
};

export default MapDashboard;
