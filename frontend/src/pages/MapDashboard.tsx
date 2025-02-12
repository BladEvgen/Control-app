import React, { useState, useEffect, useRef, useCallback } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L, { Map as LeafletMap } from "leaflet";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import Notification from "../components/Notification";
import AnimatedMarker from "../components/AnimatedMarker";
import { BaseAction } from "../schemas/BaseAction";
import { LocationData } from "../schemas/IData";
import { FaExpand, FaCompress } from "react-icons/fa";
import { motion, AnimatePresence, Variants } from "framer-motion";
import LoaderComponent from "../components/LoaderComponent";
import EditableDateField from "../components/EditableDateField";

const getFormattedDateAt = (): string => {
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  return yesterday.toISOString().split("T")[0];
};

/**
 * Расчет расстояния между двумя точками на Земле с использованием формулы Хаверсина
 * @param lat1 Широта первой точки
 * @param lon1 Долгота первой точки
 * @param lat2 Широта второй точки
 * @param lon2 Долгота второй точки
 * @returns Расстояние в километрах
 */
const calculateDistance = (
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number => {
  const R = 6371; // Радиус Земли в километрах
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

/**
 * Кастомная функция генерации различимых цветов с использованием золотого сечения
 * @param numColors Количество необходимых цветов
 * @returns Массив строковых значений цветов в формате HSL
 */
const generateDistinctColors = (numColors: number): string[] => {
  const colors: string[] = [];
  const saturation = 65;
  const lightness = 40;

  const goldenRatioConjugate = 0.618033988749895;
  let hue = Math.random();

  const excludedRanges = [{ start: 50, end: 100 }];

  const isExcluded = (h: number) => {
    return excludedRanges.some((range) => h >= range.start && h <= range.end);
  };

  while (colors.length < numColors) {
    hue += goldenRatioConjugate;
    hue %= 1;
    const h = Math.floor(hue * 360);

    if (!isExcluded(h)) {
      colors.push(`hsl(${h}, ${saturation}%, ${lightness}%)`);
    }
  }

  return colors;
};

/**
 * Функция присвоения цветов локациям с учетом близости
 * @param locations Массив локаций
 * @param distanceThreshold Порог расстояния в километрах для определения соседей
 * @returns Массив цветов, индексированный по индексам локаций
 */
const assignColors = (
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

  const colorPalette = generateDistinctColors(numLocations * 4);

  const assignedColors: string[] = Array(numLocations).fill("");
  const colorAssigned: number[] = Array(numLocations).fill(-1);

  for (let i = 0; i < numLocations; i++) {
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

    // Присвоение цвета
    colorAssigned[i] = colorIndex;
    assignedColors[i] = colorPalette[colorIndex % colorPalette.length];
  }

  return assignedColors;
};

const containerVariants: Variants = {
  hidden: { opacity: 0, y: 50 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: "easeOut" },
  },
  exit: { opacity: 0, y: -50, transition: { duration: 0.3, ease: "easeIn" } },
};

const formVariants: Variants = {
  hidden: { opacity: 0, scale: 0.8 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { delay: 0.3, duration: 0.5, ease: "easeOut" },
  },
};

const buttonVariants: Variants = {
  hover: {
    scale: 1.2,
    rotate: 15,
    transition: {
      duration: 0.3,
      repeat: Infinity,
      repeatType: "loop" as const,
      ease: "easeOut",
    },
  },
  tap: {
    scale: 0.9,
    rotate: -15,
    transition: { duration: 0.2 },
  },
  initial: {
    scale: 1,
    rotate: 0,
  },
};

const mapVariants: Variants = {
  hidden: { opacity: 0, scale: 0.95 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { delay: 0.5, duration: 0.5, ease: "easeOut" },
  },
  exit: {
    opacity: 0,
    scale: 0.95,
    transition: { duration: 0.3, ease: "easeIn" },
  },
};

const loadingVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.5 } },
  exit: { opacity: 0, transition: { duration: 0.3 } },
};

const errorVariants: Variants = {
  hidden: { opacity: 0, y: -20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.3, ease: "easeOut" },
  },
  exit: { opacity: 0, y: 20, transition: { duration: 0.2, ease: "easeIn" } },
};

const useFullscreenChange = (callback: () => void) => {
  useEffect(() => {
    const handleFullscreenChange = () => {
      callback();
    };
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [visiblePopup, setVisiblePopup] = useState<string | null>(null);
  const [isMarkersVisible, setIsMarkersVisible] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [zoomLevel, setZoomLevel] = useState<number>(13.5);
  const mapRef = useRef<LeafletMap | null>(null);
  const [assignedColors, setAssignedColors] = useState<string[]>([]);
  const [dateAt, setDateAt] = useState<string>(getFormattedDateAt());
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const formRef = useRef<HTMLDivElement>(null);

  /**
   * Функция для загрузки данных о локациях
   * @param selectedDate - Выбранная дата
   */
  const fetchLocations = async (selectedDate: string) => {
    setLoading(true);
    try {
      const response = await axiosInstance.get(
        `${apiUrl}/api/locations?employees=true&date_at=${selectedDate}`
      );
      const fetchedLocations: LocationData[] = response.data.filter(
        (loc: LocationData) => loc.employees > 0
      );
      setLocations(fetchedLocations);

      const distanceThreshold = 0.25;
      const tempAssignedColors = assignColors(
        fetchedLocations,
        distanceThreshold
      );
      setAssignedColors(tempAssignedColors);

      if (fetchedLocations.length > 0) {
        setVisiblePopup(
          `${fetchedLocations[0].name}-${fetchedLocations[0].address}-0`
        );
      }

      new BaseAction(BaseAction.SET_DATA, fetchedLocations);
    } catch (error) {
      setError("Не удалось загрузить данные.");
      new BaseAction<string>(BaseAction.SET_ERROR, "Ошибка загрузки данных");
    } finally {
      setLoading(false);
      setIsMarkersVisible(true);
    }
  };

  useEffect(() => {
    fetchLocations(dateAt);
  }, [dateAt]);

  /**
   * Обработчик изменения даты
   * @param event - Событие изменения ввода
   */
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

  /**
   * Обработчик переключения видимости попапа
   * @param location - Локация, на которую кликнули
   * @param index - Индекс локации
   */
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
    if (!isFullscreen) {
      document.documentElement.requestFullscreen?.();
      setIsFullscreen(true);
      setTimeout(() => {
        formRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      }, 300);
    } else {
      document.exitFullscreen?.();
      setIsFullscreen(false);
    }
  };

  const handleFullscreenChange = useCallback(() => {
    const isFs = !!document.fullscreenElement;
    setIsFullscreen(isFs);
  }, []);

  useFullscreenChange(handleFullscreenChange);

  const handleZoom = useCallback(() => {
    if (mapRef.current) {
      setZoomLevel(mapRef.current.getZoom());
    }
  }, []);

  if (loading)
    return (
      <motion.div
        className="flex flex-col justify-center items-center h-screen text-white"
        variants={loadingVariants}
        initial="hidden"
        animate="visible"
        exit="exit"
      >
        <LoaderComponent />
        <motion.p
          className="mt-4 text-lg font-medium text-white"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3, duration: 0.5 }}
        >
          Загрузка данных, пожалуйста, подождите...
        </motion.p>
      </motion.div>
    );

  if (error)
    return (
      <AnimatePresence>
        <motion.div
          variants={errorVariants}
          initial="hidden"
          animate="visible"
          exit="exit"
          className="flex justify-center items-center h-screen bg-red-100"
        >
          <Notification message={error} type="error" link="/" />
        </motion.div>
      </AnimatePresence>
    );

  return (
    <AnimatePresence>
      <motion.div
        className="relative h-screen w-screen"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        exit="exit"
      >
        <motion.div
          ref={formRef}
          className={`flex flex-col items-center justify-center mb-4 transition-all duration-500 ${
            isFullscreen ? "mt-4" : "mt-10"
          }`}
          variants={formVariants}
          initial="hidden"
          animate="visible"
          exit="hidden"
        >
          <EditableDateField
            label="Дата данных:"
            value={dateAt}
            onChange={handleDateChange}
            labelClassName="mb-2 text-white text-lg"
            inputClassName="w-full max-w-sm p-3 border border-gray-300 rounded-lg shadow-lg text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-base"
            displayClassName="w-full max-w-sm cursor-pointer text-center hover:underline transition-all duration-200 text-white text-base"
          />
        </motion.div>

        <motion.button
          onClick={handleFullscreenToggle}
          className="fixed top-4 right-4 sm:right-6 md:right-8 z-20 bg-white text-gray-700 p-3 rounded-full shadow-lg hover:bg-gray-100 transition-all duration-200"
          aria-label={
            isFullscreen
              ? "Выйти из полноэкранного режима"
              : "Перейти в полноэкранный режим"
          }
          variants={buttonVariants}
          initial="initial"
          whileHover="hover"
          whileTap="tap"
        >
          {isFullscreen ? (
            <FaCompress className="w-5 h-5 sm:w-6 sm:h-6 md:w-7 md:h-7" />
          ) : (
            <FaExpand className="w-5 h-5 sm:w-6 sm:h-6 md:w-7 md:h-7" />
          )}
        </motion.button>

        <motion.div
          ref={mapContainerRef}
          className="max-w-[90%] max-h-[90%] mx-auto my-4 border-2 rounded-lg shadow-lg overflow-hidden"
          style={{ padding: "2%", height: isFullscreen ? "95vh" : "80vh" }}
          variants={mapVariants}
          initial="hidden"
          animate="visible"
          exit="exit"
        >
          <MapContainer
            center={[43.2644734, 76.9393907]}
            zoom={zoomLevel}
            style={{
              width: "100%",
              height: "100%",
              borderRadius: "12px",
              boxShadow: "0 4px 12px rgba(0, 0, 0, 0.1)",
              transition: "filter 0.5s ease",
            }}
            tap={false}
          >
            <MapEventHandler mapRef={mapRef} handleZoom={handleZoom} />

            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

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
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

export default MapDashboard;
