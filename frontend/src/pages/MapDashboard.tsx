import React, { useState, useEffect, useRef } from "react";
import { MapContainer, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import Notification from "../components/Notification";
import AnimatedMarker from "../components/AnimatedMarker";
import { BaseAction } from "../schemas/BaseAction";
import { LocationData } from "../schemas/IData";
import { FaExpand, FaCompress } from "react-icons/fa";

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

const generateDistinctColors = (numColors: number, theme: string): string[] => {
  const colors = [];
  for (let i = 0; i < numColors; i++) {
    let hue = (i * 137) % 360;
    if (theme === "light" && hue >= 45 && hue <= 75) {
      hue = (hue + 90) % 360;
    }
    const saturation = theme === "dark" ? "40%" : "70%";
    const lightness = theme === "dark" ? "50%" : "50%";
    colors.push(`hsl(${hue}, ${saturation}, ${lightness})`);
  }
  return colors;
};

const MapPage: React.FC = () => {
  const [locations, setLocations] = useState<LocationData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [visiblePopup, setVisiblePopup] = useState<string | null>(null);
  const [isMarkersVisible, setIsMarkersVisible] = useState(false);
  const [theme] = useState<string>(localStorage.getItem("theme") || "light");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const mapRef = useRef<L.Map | null>(null);
  const [assignedColors, setAssignedColors] = useState<{
    [key: string]: string;
  }>({});
  const [dateAt, setDateAt] = useState<string>(getFormattedDateAt());

  const fetchLocations = async (selectedDate: string) => {
    setLoading(true);
    console.log(
      `Запрос API с параметрами: employees=true, date_at=${selectedDate}`
    );

    try {
      const response = await axiosInstance.get(
        `${apiUrl}/api/locations?employees=true&date_at=${selectedDate}`
      );
      console.log("Ответ API:", response.data);

      const fetchedLocations: LocationData[] = response.data.filter(
        (loc: LocationData) => loc.employees > 0
      );
      setLocations(fetchedLocations);

      interface LocationNode {
        location: LocationData;
        neighbors: number[];
      }

      const locationNodes: LocationNode[] = fetchedLocations.map((loc) => ({
        location: loc,
        neighbors: [],
      }));
      const distanceThreshold = 0.4;

      for (let i = 0; i < fetchedLocations.length; i++) {
        for (let j = i + 1; j < fetchedLocations.length; j++) {
          const distance = calculateDistance(
            fetchedLocations[i].lat,
            fetchedLocations[i].lng,
            fetchedLocations[j].lat,
            fetchedLocations[j].lng
          );
          if (distance < distanceThreshold) {
            locationNodes[i].neighbors.push(j);
            locationNodes[j].neighbors.push(i);
          }
        }
      }

      const numColors = Math.max(fetchedLocations.length, 20);
      const colors = generateDistinctColors(numColors, theme);
      const tempAssignedColors: { [key: string]: string } = {};
      for (let i = 0; i < locationNodes.length; i++) {
        const node = locationNodes[i];
        const usedColorIndices = new Set<number>();
        for (const neighborIndex of node.neighbors) {
          const neighbor = locationNodes[neighborIndex];
          const neighborColor = tempAssignedColors[neighbor.location.name];
          if (neighborColor) {
            const colorIndex = colors.indexOf(neighborColor);
            if (colorIndex !== -1) {
              usedColorIndices.add(colorIndex);
            }
          }
        }
        let colorAssigned = false;
        for (let colorIndex = 0; colorIndex < colors.length; colorIndex++) {
          if (!usedColorIndices.has(colorIndex)) {
            tempAssignedColors[node.location.name] = colors[colorIndex];
            colorAssigned = true;
            break;
          }
        }
        if (!colorAssigned) {
          tempAssignedColors[node.location.name] = colors[0];
        }
      }

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
    }
    setTimeout(() => setIsMarkersVisible(true), 1000);
  };

  useEffect(() => {
    fetchLocations(dateAt);
  }, [theme, dateAt]);

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
    mapRef.current?.setView(
      [location.lat, location.lng],
      mapRef.current.getZoom(),
      { animate: true }
    );
  };

  const customIcon = L.icon({
    iconUrl: `${apiUrl}/media/marker.png`,
    iconSize: [35, 40],
    iconAnchor: [17, 35],
    popupAnchor: [0, -40],
  });
  const mapContainerRef = useRef<HTMLDivElement>(null);

  const handleFullscreenToggle = () => {
    if (!isFullscreen) {
      document.documentElement.requestFullscreen?.();
      setTimeout(() => {
        mapContainerRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      }, 300);
    } else {
      document.exitFullscreen?.();
    }
    setIsFullscreen(!isFullscreen);
  };

  if (loading)
    return (
      <div className="flex flex-col justify-center items-center h-screen text-gray-700">
        <div className="loader w-16 h-16 border-4 border-gray-300 border-t-4 border-t-blue-500 rounded-full animate-spin"></div>
        <p className="mt-4 text-lg font-medium text-white">
          Загрузка данных, пожалуйста, подождите...
        </p>
      </div>
    );

  if (error) return <Notification message={error} type="error" link="/" />;

  return (
    <div className={`relative h-screen w-screen`}>
      <div className="flex flex-col items-center justify-center mb-4">
        <label className="text-white text-center mb-2">Дата данных:</label>
        <input
          type="date"
          value={dateAt}
          onChange={handleDateChange}
          className="p-2 border rounded shadow-lg text-gray-700"
        />
      </div>

      <button
        onClick={handleFullscreenToggle}
        className="absolute top-4 right-4 z-10 bg-white text-gray-700 p-2 sm:p-3 md:p-4 rounded-full shadow-lg hover:bg-gray-100 transition-all duration-200"
        aria-label={
          isFullscreen
            ? "Выйти из полноэкранного режима"
            : "Перейти в полноэкранный режим"
        }
      >
        {isFullscreen ? (
          <FaCompress className="w-5 h-5 sm:w-6 sm:h-6 md:w-7 md:h-7" />
        ) : (
          <FaExpand className="w-5 h-5 sm:w-6 sm:h-6 md:w-7 md:h-7" />
        )}
      </button>

      <div
        ref={mapContainerRef}
        className="max-w-[90%] max-h-[90%] mx-auto my-4 border-2 rounded-lg shadow-lg"
        style={{ padding: "2%", height: isFullscreen ? "95vh" : "80vh" }}
      >
        <MapContainer
          center={[43.2644734, 76.9393907]}
          zoom={13.5}
          style={{
            width: "100%",
            height: "100%",
            borderRadius: "12px",
            boxShadow: "0 4px 12px rgba(0, 0, 0, 0.1)",
          }}
          tap={false}
          ref={mapRef}
        >
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
                radius={120}
                color={assignedColors[location.name]}
              />
            );
          })}
        </MapContainer>
      </div>
    </div>
  );
};

export default MapPage;
