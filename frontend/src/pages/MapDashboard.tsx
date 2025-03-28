import React, { useState, useEffect, useRef, useCallback } from "react";
import { MapContainer, TileLayer, useMap, ZoomControl } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L, { Map as LeafletMap } from "leaflet";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import Notification from "../components/Notification";
import AnimatedMarker from "../components/AnimatedMarker";
import { BaseAction } from "../schemas/BaseAction";
import { LocationData } from "../schemas/IData";
import { FaExpand, FaCompress, FaCalendarAlt } from "react-icons/fa";
import { motion, Variants } from "framer-motion";
import LoaderComponent from "../components/LoaderComponent";
import EditableDateField from "../components/EditableDateField";

const getFormattedDateAt = (): string => {
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  return yesterday.toISOString().split("T")[0];
};

const calculateDistance = (
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
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
  distanceThreshold: number
): string[] => {
  const numLocations = locations.length;

  const adjacencyList: number[][] = Array.from(
    { length: numLocations },
    () => []
  );

  for (let i = 0; i < numLocations; i++) {
    for (let j = i + 1; j < numLocations; j++) {
      const distance = calculateDistance(
        locations[i].lat,
        locations[i].lng,
        locations[j].lat,
        locations[j].lng
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
    (_, i) => i
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
  handleZoom: () => void;
}> = ({ mapRef, handleZoom }) => {
  const map = useMap();

  useEffect(() => {
    mapRef.current = map;
    map.on("zoomend", handleZoom);
    handleZoom();

    return () => {
      map.off("zoomend", handleZoom);
    };
  }, [map, mapRef, handleZoom]);

  return null;
};

const MapDashboard: React.FC = () => {
  const [locations, setLocations] = useState<LocationData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [visiblePopup, setVisiblePopup] = useState<string | null>(null);
  const [isMarkersVisible, setIsMarkersVisible] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [zoomLevel, setZoomLevel] = useState<number>(13.5);
  const [assignedColors, setAssignedColors] = useState<string[]>([]);
  const [dateAt, setDateAt] = useState<string>(getFormattedDateAt());

  const mapRef = useRef<LeafletMap | null>(null);
  const mapContainerRef = useRef<HTMLDivElement>(null);

  const dispatch = (action: BaseAction<any>) => {
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
  };

  const fetchLocations = async (selectedDate: string) => {
    dispatch(new BaseAction(BaseAction.SET_LOADING, true));
    try {
      const response = await axiosInstance.get(
        `${apiUrl}/api/locations?employees=true&date_at=${selectedDate}`
      );
      const fetchedLocations: LocationData[] = response.data.filter(
        (loc: LocationData) => loc.employees > 0
      );

      dispatch(new BaseAction(BaseAction.SET_DATA, fetchedLocations));

      const distanceThreshold = 0.25;
      const tempAssignedColors = assignHighContrastColors(
        fetchedLocations,
        distanceThreshold
      );
      setAssignedColors(tempAssignedColors);

      if (fetchedLocations.length > 0) {
        setVisiblePopup(
          `${fetchedLocations[0].name}-${fetchedLocations[0].address}-0`
        );
      }

      setIsMarkersVisible(true);
    } catch (error) {
      dispatch(
        new BaseAction(BaseAction.SET_ERROR, "Не удалось загрузить данные.")
      );
    }
  };

  useEffect(() => {
    fetchLocations(dateAt);
  }, [dateAt]);

  useEffect(() => {
    if (locations.length > 0) {
      const timeoutId = setTimeout(() => {
        if (mapRef.current && mapRef.current.getContainer()) {
          try {
            mapRef.current.setView(
              [locations[0].lat, locations[0].lng],
              mapRef.current.getZoom(),
              {
                animate: false,
              }
            );
          } catch (error) {
            console.error("Error setting map view:", error);
          }
        }
      }, 500);

      return () => clearTimeout(timeoutId);
    }
  }, [locations]);

  const handleDateChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedDate = event.target.value;
    const today = new Date().toISOString().split("T")[0];

    if (selectedDate > today) {
      setDateAt(today);
      fetchLocations(today);
    } else {
      setDateAt(selectedDate);
      fetchLocations(selectedDate);
    }
  };

  const toggleVisibility = (location: LocationData, index: number) => {
    const identifier = `${location.name}-${location.address}-${index}`;
    setVisiblePopup(visiblePopup === identifier ? null : identifier);
    if (mapRef.current) {
      mapRef.current.setView(
        [location.lat, location.lng],
        mapRef.current.getZoom(),
        { animate: true }
      );
    }
  };

  const customIcon = L.icon({
    iconUrl: `${apiUrl}/media/marker.png`,
    iconSize: [35, 40],
    iconAnchor: [17, 35],
    popupAnchor: [0, -40],
    className: "custom-marker-icon",
  });

  const handleFullscreenToggle = () => {
    window.scrollTo(0, 0);

    setTimeout(() => {
      window.scrollTo(0, 0);

      if (mapRef.current) {
        const currentCenter = mapRef.current.getCenter();
        mapRef.current.setView(currentCenter, mapRef.current.getZoom());
      }
    }, 100);

    if (!isFullscreen) {
      if (document.documentElement.requestFullscreen) {
        document.documentElement.requestFullscreen();
      } else if ((document.documentElement as any).webkitRequestFullscreen) {
        (document.documentElement as any).webkitRequestFullscreen();
      } else if ((document.documentElement as any).mozRequestFullScreen) {
        (document.documentElement as any).mozRequestFullScreen();
      } else if ((document.documentElement as any).msRequestFullscreen) {
        (document.documentElement as any).msRequestFullscreen();
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      } else if ((document as any).webkitExitFullscreen) {
        (document as any).webkitExitFullscreen();
      } else if ((document as any).mozCancelFullScreen) {
        (document as any).mozCancelFullScreen();
      } else if ((document as any).msExitFullscreen) {
        (document as any).msExitFullscreen();
      }
    }
  };

  const handleFullscreenChange = useCallback(() => {
    const newFullscreenState =
      !!document.fullscreenElement ||
      !!(document as any).webkitFullscreenElement ||
      !!(document as any).mozFullScreenElement ||
      !!(document as any).msFullscreenElement;

    setIsFullscreen(newFullscreenState);

    setTimeout(() => {
      window.scrollTo(0, 0);

      if (mapRef.current) {
        const currentCenter = mapRef.current.getCenter();
        mapRef.current.invalidateSize();
        mapRef.current.setView(currentCenter, mapRef.current.getZoom());
      }
    }, 300);
  }, []);

  useFullscreenChange(handleFullscreenChange);

  const handleZoom = useCallback(() => {
    if (mapRef.current) {
      setZoomLevel(mapRef.current.getZoom());
    }
  }, []);

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

      <motion.div
        className="absolute top-4 right-6 z-10 bg-white dark:bg-gray-800 rounded-lg shadow-lg overflow-hidden"
        variants={dateVariants}
        initial="hidden"
        animate="visible"
      >
        <div className="p-4 flex items-center gap-3">
          <FaCalendarAlt className="text-primary-600 dark:text-primary-400" />
          <div>
            <EditableDateField
              label="Дата данных"
              value={dateAt}
              onChange={handleDateChange}
              containerClassName="m-0 p-0"
              labelClassName="text-xs text-gray-500 dark:text-gray-400 mb-0 mr-2"
              displayClassName="font-medium text-gray-800 dark:text-gray-200 hover:text-primary-600 dark:hover:text-primary-400 cursor-pointer"
            />
          </div>
        </div>
      </motion.div>

      <motion.button
        onClick={handleFullscreenToggle}
        className="absolute top-4 left-4 z-20 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 p-3 rounded-full shadow-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-all duration-200"
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
        {isFullscreen ? (
          <FaCompress className="w-5 h-5" />
        ) : (
          <FaExpand className="w-5 h-5" />
        )}
      </motion.button>

      <div className="flex justify-center items-center w-full h-screen py-8 px-4">
        <motion.div
          ref={mapContainerRef}
          variants={mapContainerVariants}
          initial="hidden"
          animate="visible"
          className={`relative transition-all duration-700 ease-in-out ${
            isFullscreen
              ? "w-[105%] h-[98vh] -mx-6"
              : "w-[85%] h-[70vh] mx-auto"
          }`}
        >
          <div
            className={`w-full h-full overflow-hidden shadow-2xl transition-all duration-700 ease-in-out ${
              isFullscreen
                ? "rounded-none"
                : "rounded-xl border-4 border-gray-800"
            }`}
            style={{
              boxShadow: isFullscreen
                ? "0 0 40px 10px rgba(0, 0, 0, 0.5)"
                : "0 4px 30px rgba(0, 0, 0, 0.5)",
            }}
          >
            <MapContainer
              center={[54.328962, 48.389899]}
              zoom={zoomLevel}
              style={{ width: "100%", height: "100%" }}
              zoomControl={false}
              className="z-10"
            >
              <ZoomControl position="bottomright" />
              <MapEventHandler mapRef={mapRef} handleZoom={handleZoom} />

              <TileLayer
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              />

              {locations.map((location, index) => {
                const identifier = `${location.name}-${location.address}-${index}`;
                return (
                  <AnimatedMarker
                    key={identifier}
                    position={[location.lat, location.lng]}
                    name={location.name}
                    address={location.address}
                    employees={location.employees}
                    isVisible={isMarkersVisible}
                    icon={customIcon}
                    onClick={() => toggleVisibility(location, index)}
                    popupVisible={visiblePopup === identifier}
                    radius={160}
                    color={assignedColors[index]}
                    zoomLevel={zoomLevel}
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
