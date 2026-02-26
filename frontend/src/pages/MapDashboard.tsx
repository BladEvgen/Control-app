import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { MapContainer, TileLayer, useMap, ZoomControl } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L, { Map as LeafletMap } from "leaflet";
import { useLocation, useNavigate } from "react-router-dom";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import Notification from "../components/Notification";
import AnimatedMarker from "../components/AnimatedMarker";
import { BaseAction } from "../schemas/BaseAction";
import { LocationData } from "../schemas/IData";
import { FaExpand, FaCompress, FaCalendarAlt } from "react-icons/fa";
import { FiClock, FiCrosshair, FiMapPin, FiMaximize2, FiUsers } from "react-icons/fi";
import { motion, Variants } from "framer-motion";
import LoaderComponent from "../components/LoaderComponent";
import EditableDateField from "../components/EditableDateField";
import { useAppSelector } from "../store/hooks";

type MapDispatchPayload = boolean | LocationData[] | string;
type MapFocusMode = "first" | "all";

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
const MAP_DEFAULT_ZOOM = 13.5;
const MAP_MULTI_POINT_ZOOM = 15;
const MAP_SINGLE_POINT_ZOOM = 16;
const NUMBER_FORMATTER = new Intl.NumberFormat("ru-RU");

const getFormattedDateAt = (): string => {
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  return yesterday.toISOString().split("T")[0];
};

const calculateDistance = (
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number => {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  return R * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)));
};

const generateVibrantColors = (numColors: number): string[] => {
  const vibrantColors = [
    "#FF0000", // Bright Red
    "#0066FF", // Bright Blue
    "#00CC00", // Vibrant Green
    "#FF6600", // Bright Orange
    "#9900FF", // Bright Purple
    "#00CCFF", // Bright Cyan
    "#FF0099", // Bright Magenta
    "#FFCC00", // Bright Yellow
    "#3300FF", // Bright Indigo
    "#66FF00", // Vibrant Lime
    "#FF3300", // Vibrant Deep Orange
    "#00FFCC", // Vibrant Teal
    "#CC00FF", // Vibrant Deep Purple
    "#FFAA00", // Vibrant Amber
    "#0099FF", // Vibrant Light Blue
    "#FF0066", // Vibrant Pink
    "#33FF00", // Vibrant Light Green
    "#FFDD00", // Vibrant Yellow
    "#0033FF", // Vibrant Deep Blue
    "#FF9900", // Vibrant Orange
  ];

  const colors: string[] = [];

  if (numColors <= vibrantColors.length) {
    return vibrantColors.slice(0, numColors);
  }

  colors.push(...vibrantColors);

  const secondaryColors = vibrantColors.map((color) => {
    const r = parseInt(color.slice(1, 3), 16);
    const g = parseInt(color.slice(3, 5), 16);
    const b = parseInt(color.slice(5, 7), 16);

    const brighterColor = `#${Math.min(255, Math.floor(r * 1.2))
      .toString(16)
      .padStart(2, "0")}${Math.min(255, Math.floor(g * 1.2))
      .toString(16)
      .padStart(2, "0")}${Math.min(255, Math.floor(b * 1.2))
      .toString(16)
      .padStart(2, "0")}`;

    return brighterColor;
  });

  colors.push(...secondaryColors);

  if (colors.length < numColors) {
    for (let i = colors.length; i < numColors; i++) {
      const r = Math.floor(Math.random() * 155 + 100)
        .toString(16)
        .padStart(2, "0");
      const g = Math.floor(Math.random() * 155 + 100)
        .toString(16)
        .padStart(2, "0");
      const b = Math.floor(Math.random() * 155 + 100)
        .toString(16)
        .padStart(2, "0");
      colors.push(`#${r}${g}${b}`);
    }
  }

  return colors;
};

const assignHighContrastColors = (
  locations: LocationData[],
  distanceThreshold: number,
): string[] => {
  const numLocations = locations.length;

  const adjacencyList: number[][] = Array.from(
    { length: numLocations },
    () => [],
  );

  for (let i = 0; i < numLocations; i++) {
    for (let j = i + 1; j < numLocations; j++) {
      const distance = calculateDistance(
        locations[i].lat,
        locations[i].lng,
        locations[j].lat,
        locations[j].lng,
      );
      if (distance <= distanceThreshold) {
        adjacencyList[i].push(j);
        adjacencyList[j].push(i);
      }
    }
  }

  const colorPalette = generateVibrantColors(Math.max(numLocations * 2, 40));

  const assignedColors: string[] = Array(numLocations).fill("");
  const colorAssigned: number[] = Array(numLocations).fill(-1);

  const locationIndices = Array.from(
    { length: numLocations },
    (_, i) => i,
  ).sort((a, b) => adjacencyList[b].length - adjacencyList[a].length);

  for (const i of locationIndices) {
    const usedColors = new Set<number>();

    for (const neighbor of adjacencyList[i]) {
      if (colorAssigned[neighbor] !== -1) {
        usedColors.add(colorAssigned[neighbor]);
      }
    }

    let colorIndex = 0;
    while (usedColors.has(colorIndex)) {
      colorIndex++;
    }

    colorAssigned[i] = colorIndex;
    assignedColors[i] = colorPalette[colorIndex % colorPalette.length];
  }

  return assignedColors;
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
}> = ({ mapRef, onMapReady }) => {
  const map = useMap();

  useEffect(() => {
    mapRef.current = map;
    onMapReady();
  }, [map, mapRef, onMapReady]);

  return null;
};

const MapDashboard: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const isKiosk =
    /\/map$/.test(location.pathname) &&
    new URLSearchParams(location.search).get("kiosk") === "1";

  const [locations, setLocations] = useState<LocationData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [visiblePopup, setVisiblePopup] = useState<string | null>(null);
  const [isMarkersVisible, setIsMarkersVisible] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isFullscreenBusy, setIsFullscreenBusy] = useState(false);
  const [mapReadyVersion, setMapReadyVersion] = useState(0);
  const [mapFocusMode, setMapFocusMode] = useState<MapFocusMode>("first");
  const [assignedColors, setAssignedColors] = useState<string[]>([]);
  const [dateAt, setDateAt] = useState<string>(getFormattedDateAt());
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [suppressAutoPanPopupId, setSuppressAutoPanPopupId] = useState<
    string | null
  >(null);
  const reportsAutoRefreshMinutes = useAppSelector(
    (state) => state.ui.reportsAutoRefreshMinutes,
  );

  const mapRef = useRef<LeafletMap | null>(null);
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const fullscreenToggleLockRef = useRef(false);
  const restoreKioskSearchOnExitRef = useRef(false);
  const shouldFitOnNextDataRef = useRef(true);
  const hasAutoOpenedPopupRef = useRef(false);
  const visiblePopupRef = useRef<string | null>(null);

  useEffect(() => {
    visiblePopupRef.current = visiblePopup;
  }, [visiblePopup]);

  const getLocationIdentifier = useCallback(
    (loc: LocationData, index: number) =>
      `${loc.name}-${loc.address}-${loc.lat}-${loc.lng}-${index}`,
    [],
  );

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

  const totalEmployees = useMemo(
    () => locations.reduce((sum, loc) => sum + loc.employees, 0),
    [locations],
  );

  const lastUpdatedLabel = useMemo(() => {
    if (!lastUpdatedAt) return "ожидание";
    return new Intl.DateTimeFormat("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(lastUpdatedAt);
  }, [lastUpdatedAt]);

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
    async (selectedDate: string) => {
      dispatch(new BaseAction(BaseAction.SET_LOADING, true));
      try {
        const response = await axiosInstance.get(
          `${apiUrl}/api/locations?employees=true&date_at=${selectedDate}`,
        );
        const fetchedLocations: LocationData[] = response.data.filter(
          (loc: LocationData) => loc.employees > 0,
        );

        dispatch(new BaseAction(BaseAction.SET_DATA, fetchedLocations));

        const distanceThreshold = 0.25;
        const tempAssignedColors = assignHighContrastColors(
          fetchedLocations,
          distanceThreshold,
        );
        setAssignedColors(tempAssignedColors);
        setLastUpdatedAt(new Date());

        const fetchedIdentifiers = fetchedLocations.map((loc, index) =>
          getLocationIdentifier(loc, index),
        );
        const currentVisiblePopup = visiblePopupRef.current;
        const hasCurrentVisible =
          currentVisiblePopup !== null &&
          fetchedIdentifiers.includes(currentVisiblePopup);

        if (hasCurrentVisible) {
          setVisiblePopup(currentVisiblePopup);
          setSuppressAutoPanPopupId(null);
        } else if (!hasAutoOpenedPopupRef.current && fetchedIdentifiers[0]) {
          const firstPopupId = fetchedIdentifiers[0];
          setVisiblePopup(firstPopupId);
          setSuppressAutoPanPopupId(firstPopupId);
          hasAutoOpenedPopupRef.current = true;
        } else {
          setVisiblePopup(null);
          setSuppressAutoPanPopupId(null);
        }

        setIsMarkersVisible(true);
      } catch {
        dispatch(
          new BaseAction(BaseAction.SET_ERROR, "Не удалось загрузить данные."),
        );
      }
    },
    [dispatch, getLocationIdentifier],
  );

  useEffect(() => {
    fetchLocations(dateAt);
  }, [dateAt, fetchLocations]);

  useEffect(() => {
    if (locations.length === 0) {
      shouldFitOnNextDataRef.current = true;
    }
  }, [locations.length]);

  useEffect(() => {
    if (reportsAutoRefreshMinutes <= 0) return;
    const intervalMs = reportsAutoRefreshMinutes * 60 * 1000;
    const id = window.setInterval(() => fetchLocations(dateAt), intervalMs);
    return () => clearInterval(id);
  }, [dateAt, reportsAutoRefreshMinutes, fetchLocations]);

  const handleDateChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedDate = event.target.value;
    const today = new Date().toISOString().split("T")[0];

    if (selectedDate > today) {
      setDateAt(today);
    } else {
      setDateAt(selectedDate);
    }
    setMapFocusMode("first");
    shouldFitOnNextDataRef.current = true;
  };

  const toggleVisibility = (location: LocationData, index: number) => {
    const identifier = getLocationIdentifier(location, index);
    const nextVisiblePopup = visiblePopup === identifier ? null : identifier;
    setSuppressAutoPanPopupId(null);
    setVisiblePopup(nextVisiblePopup);

    if (nextVisiblePopup) {
      toggleMapOnMarkerClick(location, !isFullscreenBusy);
    }
  };

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
      } catch (error) {
        console.warn("Map setView failed, fallback to non-animated view.", error);
        try {
          map.invalidateSize();
          map.setView(center, zoom, { animate: false });
          return true;
        } catch (fallbackError) {
          console.error("Map setView fallback failed.", fallbackError);
          return false;
        }
      }
    },
    [],
  );

  const safeFitBounds = useCallback(
    (bounds: L.LatLngBounds, animate: boolean, maxZoom: number): boolean => {
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
          padding: [72, 72],
          maxZoom,
          animate,
        });
        return true;
      } catch (error) {
        console.warn(
          "Map fitBounds failed, fallback to non-animated fit.",
          error,
        );
        try {
          map.invalidateSize();
          map.fitBounds(bounds, {
            padding: [72, 72],
            maxZoom,
            animate: false,
          });
          return true;
        } catch (fallbackError) {
          console.error("Map fitBounds fallback failed.", fallbackError);
          return false;
        }
      }
    },
    [],
  );

  const toggleMapViewToLocation = useCallback(
    (location: LocationData, animate: boolean) => {
      const map = mapRef.current;
      if (!map) return;

      safeSetView([location.lat, location.lng], map.getZoom(), animate);
    },
    [safeSetView],
  );

  const toggleMapOnMarkerClick = useCallback(
    (location: LocationData, shouldAnimate: boolean) => {
      if (!shouldAnimate) {
        toggleMapViewToLocation(location, false);
        return;
      }
      toggleMapViewToLocation(location, true);
    },
    [toggleMapViewToLocation],
  );

  const centerMapOnFirstLocation = useCallback((animate = false): boolean => {
    if (locations.length === 0) {
      return safeSetView(MAP_DEFAULT_CENTER, MAP_DEFAULT_ZOOM, false);
    }

    const [firstLocation] = locations;
    const targetZoom =
      locations.length === 1 ? MAP_SINGLE_POINT_ZOOM : MAP_MULTI_POINT_ZOOM;
    return safeSetView([firstLocation.lat, firstLocation.lng], targetZoom, animate);
  }, [locations, safeSetView]);

  const fitMapToAllLocations = useCallback((animate = true): boolean => {
    if (locations.length === 0) {
      return safeSetView(MAP_DEFAULT_CENTER, MAP_DEFAULT_ZOOM, false);
    }

    if (locations.length === 1) {
      return centerMapOnFirstLocation(animate);
    }

    const bounds = L.latLngBounds(
      locations.map((loc) => [loc.lat, loc.lng] as [number, number]),
    );
    if (!bounds.isValid()) return false;

    return safeFitBounds(bounds, animate, MAP_MULTI_POINT_ZOOM);
  }, [centerMapOnFirstLocation, locations, safeFitBounds, safeSetView]);

  const handleFocusFirst = useCallback(() => {
    setMapFocusMode("first");
    centerMapOnFirstLocation(true);
  }, [centerMapOnFirstLocation]);

  const handleFocusAll = useCallback(() => {
    setMapFocusMode("all");
    fitMapToAllLocations(true);
  }, [fitMapToAllLocations]);

  const handleMapReady = useCallback(() => {
    setMapReadyVersion((prev) => prev + 1);
  }, []);

  const handleFullscreenToggle = useCallback(async () => {
    if (fullscreenToggleLockRef.current) return;

    const docEl = document.documentElement as DocumentElementWithFullscreen;
    const doc = document as DocumentWithFullscreen;
    const currentlyFullscreen = !!getFullscreenElement();

    fullscreenToggleLockRef.current = true;
    setIsFullscreenBusy(true);

    try {
      if (!currentlyFullscreen) {
        if (!isKiosk) {
          restoreKioskSearchOnExitRef.current = true;
          navigate(
            { pathname: location.pathname, search: "?kiosk=1" },
            { replace: true },
          );
          await new Promise<void>((resolve) => window.setTimeout(resolve, 120));
        }

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
    } catch (error) {
      console.error("Error toggling fullscreen:", error);
    } finally {
      window.setTimeout(() => {
        if (!getFullscreenElement()) {
          setIsFullscreenBusy(false);
          fullscreenToggleLockRef.current = false;
        }
      }, 350);
    }
  }, [getFullscreenElement, isKiosk, location.pathname, navigate]);

  const handleFullscreenChange = useCallback(() => {
    const newFullscreenState = !!getFullscreenElement();
    setIsFullscreen(newFullscreenState);
    setIsFullscreenBusy(false);
    fullscreenToggleLockRef.current = false;

    if (!newFullscreenState && restoreKioskSearchOnExitRef.current) {
      restoreKioskSearchOnExitRef.current = false;
      if (new URLSearchParams(window.location.search).get("kiosk") === "1") {
        navigate(
          { pathname: location.pathname, search: "" },
          { replace: true },
        );
      }
    }

    window.setTimeout(() => {
      if (!mapRef.current) return;
      mapRef.current.invalidateSize();
    }, 480);
  }, [getFullscreenElement, location.pathname, navigate]);

  useFullscreenChange(handleFullscreenChange);

  useEffect(() => {
    if (!shouldFitOnNextDataRef.current) return;

    let attempts = 0;

    const tryCenter = () => {
      const centered = centerMapOnFirstLocation();
      if (centered) {
        shouldFitOnNextDataRef.current = false;
        setMapFocusMode("first");
      }
      return centered;
    };

    if (tryCenter()) {
      return;
    }

    const id = window.setInterval(() => {
      attempts += 1;
      if (tryCenter() || attempts >= 25) {
        window.clearInterval(id);
      }
    }, 120);

    return () => window.clearInterval(id);
  }, [centerMapOnFirstLocation, locations, mapReadyVersion]);

  useEffect(() => {
    const el = mapContainerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    let resizeTimeout: number | null = null;
    const ro = new ResizeObserver(() => {
      if (resizeTimeout !== null) {
        window.clearTimeout(resizeTimeout);
      }
      resizeTimeout = window.setTimeout(() => {
        if (mapRef.current) {
          mapRef.current.invalidateSize();
        }
      }, 120);
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      if (resizeTimeout !== null) {
        window.clearTimeout(resizeTimeout);
      }
    };
  }, []);

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
      window.scrollTo(0, 0);
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen ">
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
      className="relative min-h-screen bg-gradient-to-b "
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
    >
      <div
        className="absolute inset-0 z-0 opacity-10 pointer-events-none"
        style={{
          backgroundImage:
            "radial-gradient(rgba(255,255,255,0.1) 1px, transparent 1px)",
          backgroundSize: "30px 30px",
        }}
      />

      <div
        className={`relative z-20 mx-auto w-full max-w-[1600px] px-3 sm:px-4 ${
          isFullscreen ? "pt-2 pb-2" : "pt-4 sm:pt-5 pb-3"
        }`}
      >
        <motion.div
          className={`rounded-2xl border px-3 sm:px-4 py-2.5 sm:py-3 shadow-lg backdrop-blur-md flex flex-wrap items-center justify-between gap-3 ${
            isFullscreen
              ? "border-white/55 dark:border-slate-700/70 bg-white/65 dark:bg-slate-900/45"
              : "border-white/65 dark:border-slate-700/80 bg-white/70 dark:bg-slate-900/55"
          }`}
          variants={dateVariants}
          initial="hidden"
          animate="visible"
        >
          <div className="min-w-0">
            <h1 className="text-lg sm:text-xl font-semibold text-gray-800 dark:text-gray-100 truncate">
              Карта посещаемости
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 sm:gap-2 text-[11px] sm:text-xs">
              <span className="inline-flex items-center gap-1 rounded-full border border-sky-200/90 dark:border-sky-700/70 bg-sky-50/90 dark:bg-sky-900/30 px-2 py-0.5 text-sky-700 dark:text-sky-200">
                <FiMapPin className="w-3 h-3" />
                {NUMBER_FORMATTER.format(locations.length)} точек
              </span>
              <span className="inline-flex items-center gap-1 rounded-full border border-violet-200/90 dark:border-violet-700/70 bg-violet-50/90 dark:bg-violet-900/30 px-2 py-0.5 text-violet-700 dark:text-violet-200">
                <FiUsers className="w-3 h-3" />
                {NUMBER_FORMATTER.format(totalEmployees)} посещений
              </span>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <div className="inline-flex items-center gap-2 px-2.5 sm:px-3 py-1.5 rounded-lg border border-white/50 dark:border-slate-700/80 bg-white/55 dark:bg-slate-900/55">
              <FaCalendarAlt className="text-primary-600 dark:text-primary-400" />
              <EditableDateField
                label="Дата данных"
                value={dateAt}
                onChange={handleDateChange}
                containerClassName="m-0 p-0"
                labelClassName="text-xs text-gray-500 dark:text-gray-400 mb-0 mr-2"
                displayClassName="font-medium text-gray-800 dark:text-gray-200 hover:text-primary-600 dark:hover:text-primary-400 cursor-pointer"
              />
            </div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-white/50 dark:border-slate-700/80 bg-white/55 dark:bg-slate-900/55 text-[11px] sm:text-xs text-gray-700 dark:text-gray-300">
              <FiClock className="w-3.5 h-3.5 text-primary-600 dark:text-primary-400" />
              Обновлено: {lastUpdatedLabel}
            </div>
            <motion.button
              onClick={handleFocusFirst}
              className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
                mapFocusMode === "first"
                  ? "border-primary-400/80 bg-primary-500/15 text-primary-700 dark:text-primary-200"
                  : "border-slate-300 dark:border-slate-600 bg-white/75 dark:bg-slate-900/70 text-slate-700 dark:text-slate-200 hover:bg-white dark:hover:bg-slate-800"
              }`}
              variants={buttonVariants}
              initial="initial"
              whileHover="hover"
              whileTap="tap"
            >
              <FiCrosshair className="w-4 h-4" />
              К первой точке
            </motion.button>
            <motion.button
              onClick={handleFocusAll}
              className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
                mapFocusMode === "all"
                  ? "border-primary-400/80 bg-primary-500/15 text-primary-700 dark:text-primary-200"
                  : "border-slate-300 dark:border-slate-600 bg-white/75 dark:bg-slate-900/70 text-slate-700 dark:text-slate-200 hover:bg-white dark:hover:bg-slate-800"
              }`}
              variants={buttonVariants}
              initial="initial"
              whileHover="hover"
              whileTap="tap"
            >
              <FiMaximize2 className="w-4 h-4" />
              Все точки
            </motion.button>
            <motion.button
              onClick={handleFullscreenToggle}
              disabled={isFullscreenBusy}
              className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white transition-colors ${
                isFullscreenBusy
                  ? "bg-primary-400 cursor-not-allowed"
                  : "bg-primary-600 hover:bg-primary-700"
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
                <FaCompress className="w-4 h-4" />
              ) : (
                <FaExpand className="w-4 h-4" />
              )}
              <span>
                {isFullscreenBusy
                  ? isFullscreen
                    ? "Выход..."
                    : "Открытие..."
                  : isFullscreen
                    ? "Выход"
                    : "Полный экран"}
              </span>
            </motion.button>
          </div>
        </motion.div>
      </div>

      <div
        className={`relative z-10 mx-auto w-full ${
          isFullscreen
            ? "max-w-none px-2 sm:px-3 pb-2 sm:pb-3"
            : "max-w-[1600px] px-3 sm:px-4 pb-3 sm:pb-4"
        } ${isFullscreen ? "h-[calc(100vh-112px)]" : "h-[clamp(420px,72vh,860px)]"} transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]`}
      >
        <motion.div
          ref={mapContainerRef}
          variants={mapContainerVariants}
          initial="hidden"
          animate="visible"
          className="relative w-full h-full"
        >
          <div
            className={`relative w-full h-full overflow-hidden transition-all duration-500 ${
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

            <MapContainer
              center={MAP_DEFAULT_CENTER}
              zoom={MAP_DEFAULT_ZOOM}
              style={{ width: "100%", height: "100%" }}
              zoomControl={false}
              attributionControl={false}
              className="z-10"
            >
              <ZoomControl position="bottomright" />
              <MapEventHandler mapRef={mapRef} onMapReady={handleMapReady} />

              <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

              {locations.map((location, index) => {
                const identifier = getLocationIdentifier(location, index);
                return (
                  <AnimatedMarker
                    key={identifier}
                    position={[location.lat, location.lng]}
                    name={location.name}
                    address={location.address}
                    employees={location.employees}
                    isVisible={isMarkersVisible}
                    onClick={() => toggleVisibility(location, index)}
                    popupVisible={visiblePopup === identifier}
                    autoPan={
                      suppressAutoPanPopupId !== identifier && !isFullscreenBusy
                    }
                    radius={96}
                    color={assignedColors[index]}
                  />
                );
              })}
            </MapContainer>
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
};

export default MapDashboard;
