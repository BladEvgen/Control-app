import React, { useEffect, useRef, useState } from "react";
import { Marker, Circle, Popup } from "react-leaflet";
import L from "leaflet";
import { motion, AnimatePresence } from "framer-motion";

interface AnimatedMarkerProps {
  position: [number, number];
  name: string;
  address: string;
  employees: number;
  isVisible: boolean;
  icon: L.Icon | null;
  onClick: () => void;
  popupVisible: boolean;
  radius: number;
  color: string;
  zoomLevel: number;
}

const getIconPoints = (
  pointExpression?: L.PointExpression
): [number, number] => {
  if (!pointExpression) {
    return [35, 40];
  }
  if (Array.isArray(pointExpression)) {
    return [pointExpression[0], pointExpression[1]];
  } else if (pointExpression instanceof L.Point) {
    return [pointExpression.x, pointExpression.y];
  } else {
    return [35, 40];
  }
};

const AnimatedMarker: React.FC<AnimatedMarkerProps> = ({
  position,
  name,
  address,
  employees,
  isVisible,
  icon,
  onClick,
  popupVisible,
  radius,
  color,
  zoomLevel,
}) => {
  const markerRef = useRef<L.Marker | null>(null);
  const [pulse, setPulse] = useState(false);

  useEffect(() => {
    if (isVisible) {
      const interval = setInterval(() => {
        setPulse((prev) => !prev);
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [isVisible]);

  const getScaleFactor = (zoom: number): number => {
    const baseZoom = 13.5;
    const scale = 1 + (zoom - baseZoom) * 0.1;
    return Math.max(0.7, Math.min(scale, 2));
  };

  const scaleFactor = getScaleFactor(zoomLevel);

  const iconSize = getIconPoints(icon?.options.iconSize);
  const iconAnchor = getIconPoints(icon?.options.iconAnchor);
  const popupAnchor = getIconPoints(icon?.options.popupAnchor);

  const scaledIconSize: [number, number] = [
    iconSize[0] * scaleFactor,
    iconSize[1] * scaleFactor,
  ];
  const scaledIconAnchor: [number, number] = [
    iconAnchor[0] * scaleFactor,
    iconAnchor[1] * scaleFactor,
  ];
  const scaledPopupAnchor: [number, number] = [
    popupAnchor[0] * scaleFactor,
    popupAnchor[1] * scaleFactor,
  ];

  const scaledCustomIcon = icon
    ? L.icon({
        ...icon.options,
        iconSize: scaledIconSize,
        iconAnchor: scaledIconAnchor,
        popupAnchor: scaledPopupAnchor,
        className: "animated-marker-icon",
      })
    : null;

  const getComplementaryColor = (hexColor: string): string => {
    try {
      const r = parseInt(hexColor.slice(1, 3), 16);
      const g = parseInt(hexColor.slice(3, 5), 16);
      const b = parseInt(hexColor.slice(5, 7), 16);

      const brighterR = Math.min(255, Math.floor(r * 1.3))
        .toString(16)
        .padStart(2, "0");
      const brighterG = Math.min(255, Math.floor(g * 1.3))
        .toString(16)
        .padStart(2, "0");
      const brighterB = Math.min(255, Math.floor(b * 1.3))
        .toString(16)
        .padStart(2, "0");

      return `#${brighterR}${brighterG}${brighterB}`;
    } catch {
      return "#FFFFFF";
    }
  };

  const complementaryColor = getComplementaryColor(color);

  useEffect(() => {
    const marker = markerRef.current;
    if (marker) {
      if (popupVisible) {
        marker.openPopup();
      } else {
        marker.closePopup();
      }
    }
  }, [popupVisible]);

  useEffect(() => {
    if (popupVisible && markerRef.current) {
      const timeoutId = setTimeout(() => {
        try {
          if (markerRef.current && markerRef.current.getPopup) {
            const popup = markerRef.current.getPopup();
            if (popup) {
              const popupElement = popup.getElement();
              if (popupElement) {
                popupElement.style.display = "none";
                void popupElement.offsetHeight;
                popupElement.style.display = "";
              }
            }
          }
        } catch (error) {
          console.error("Error handling popup:", error);
        }
      }, 100);

      return () => clearTimeout(timeoutId);
    }
  }, [popupVisible]);

  return (
    <>
      {isVisible && (
        <>
          <Circle
            center={position}
            radius={radius}
            pathOptions={{
              color: color,
              fillOpacity: 0.25,
              weight: 2,
              opacity: 0.8,
              fillColor: color,
            }}
            className="animated-circle-outer"
          />

          <Marker
            ref={markerRef}
            position={position}
            icon={scaledCustomIcon || undefined}
            eventHandlers={{
              click: onClick,
            }}
          >
            <Popup
              autoPan={true}
              closeButton={true}
              minWidth={300}
              maxWidth={360}
              className="custom-popup"
              offset={[0, -35]}
            >
              <AnimatePresence>
                <motion.div
                  className="p-3 rounded-lg bg-white dark:bg-gray-800 shadow-lg border-t-4"
                  style={{ borderColor: color }}
                  initial={{ opacity: 0, y: -10, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  transition={{ duration: 0.3 }}
                >
                  <h2
                    className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-2 pb-2 border-b border-gray-200 dark:border-gray-700"
                    style={{
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      wordBreak: "break-word",
                      hyphens: "auto",
                      maxHeight: "4rem",
                    }}
                  >
                    {name}
                  </h2>

                  <div className="flex items-start gap-2 mb-3">
                    <svg
                      className="w-4 h-4 text-primary-600 dark:text-primary-400 mt-0.5 flex-shrink-0"
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                      <circle cx="12" cy="10" r="3"></circle>
                    </svg>
                    <p
                      className="text-xs text-gray-700 dark:text-gray-300"
                      style={{
                        wordBreak: "break-word",
                        hyphens: "auto",
                        maxHeight: "4rem",
                        overflow: "hidden",
                      }}
                    >
                      {address}
                    </p>
                  </div>

                  <div
                    className="flex items-center justify-between rounded-lg px-3 py-2"
                    style={{
                      background: `linear-gradient(135deg, ${color}20, ${complementaryColor}40)`,
                      borderLeft: `4px solid ${color}`,
                    }}
                  >
                    <svg
                      className="w-5 h-5"
                      style={{ color: color }}
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                      <circle cx="9" cy="7" r="4"></circle>
                      <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                      <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                    </svg>
                    <div className="flex-1 pl-2">
                      <p className="text-xs font-medium dark:text-gray-300">
                        Посещения:
                      </p>
                      <p className="text-lg font-bold" style={{ color: color }}>
                        {employees}
                      </p>
                    </div>
                  </div>
                </motion.div>
              </AnimatePresence>
            </Popup>
          </Marker>

          <Circle
            center={position}
            radius={pulse ? 36 : 30}
            pathOptions={{
              color: color,
              fillColor: complementaryColor,
              fillOpacity: 0.4,
              weight: 2,
              opacity: 0.9,
            }}
            className="marker-pulse"
          />

          <Circle
            center={position}
            radius={18}
            pathOptions={{
              color: color,
              fillColor: color,
              fillOpacity: 0.5,
              weight: 1.5,
              opacity: 0.7,
            }}
          />

          <Circle
            center={position}
            radius={radius * 0.4}
            pathOptions={{
              color: complementaryColor,
              fillColor: "transparent",
              weight: 1.5,
              opacity: 0.6,
              dashArray: "4,8",
            }}
            className="marker-highlight-rotating"
          />
        </>
      )}
    </>
  );
};

export default AnimatedMarker;
