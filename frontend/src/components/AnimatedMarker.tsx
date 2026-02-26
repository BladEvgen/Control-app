import React, { useEffect, useMemo, useRef } from "react";
import { Circle, Marker, Popup } from "react-leaflet";
import L from "leaflet";
import { motion } from "framer-motion";
import { FiMapPin, FiUsers } from "react-icons/fi";

interface AnimatedMarkerProps {
  position: [number, number];
  name: string;
  address: string;
  employees: number;
  isVisible: boolean;
  onClick: () => void;
  popupVisible: boolean;
  autoPan?: boolean;
  radius: number;
  color: string;
}

const HEX_COLOR_RE = /^#([\da-f]{3}|[\da-f]{6})$/i;

const getSafeColor = (value: string): string =>
  HEX_COLOR_RE.test(value) ? value : "#ef4444";

const getEmployeesBadge = (value: number): string => {
  if (value > 999) return "999+";
  if (value > 99) return "99+";
  return String(Math.max(0, Math.floor(value)));
};

const AnimatedMarker: React.FC<AnimatedMarkerProps> = ({
  position,
  name,
  address,
  employees,
  isVisible,
  onClick,
  popupVisible,
  autoPan = true,
  radius,
  color,
}) => {
  const markerRef = useRef<L.Marker | null>(null);
  const safeColor = useMemo(() => getSafeColor(color), [color]);

  const markerScale = useMemo(() => {
    return Math.min(1.2, Math.max(0.95, 0.95 + employees * 0.01));
  }, [employees]);

  const markerIcon = useMemo(() => {
    const employeesBadge = getEmployeesBadge(employees);

    return L.divIcon({
      className: "map-pin-icon-wrapper",
      iconSize: [48, 58],
      iconAnchor: [24, 46],
      popupAnchor: [0, -38],
      html: `
        <div class="map-pin-icon ${popupVisible ? "is-active" : ""}" style="--pin-color:${safeColor};--pin-scale:${markerScale};">
          <span class="map-pin-wave"></span>
          <span class="map-pin-core"><span class="map-pin-core-dot"></span></span>
          <span class="map-pin-badge">${employeesBadge}</span>
        </div>
      `,
    });
  }, [employees, markerScale, popupVisible, safeColor]);

  useEffect(() => {
    const marker = markerRef.current;
    if (!marker) return;

    if (popupVisible) {
      try {
        marker.openPopup();
      } catch (error) {
        console.warn("Leaflet popup open failed:", error);
      }
      return;
    }

    try {
      marker.closePopup();
    } catch (error) {
      console.warn("Leaflet popup close failed:", error);
    }
  }, [popupVisible]);

  if (!isVisible) {
    return null;
  }

  const auraRadius = Math.max(118, Math.min(radius + employees * 1.45, 260));
  const perimeterRadius = Math.max(72, Math.min(auraRadius * 0.72, 180));
  const waveRadius = Math.max(96, Math.min(auraRadius * 1.08, 275));
  const normalizedAddress = address?.trim() || "Адрес не указан";

  return (
    <>
      <Circle
        center={position}
        radius={auraRadius}
        pathOptions={{
          color: safeColor,
          fillColor: safeColor,
          fillOpacity: 0.24,
          weight: 2.8,
          opacity: 0.88,
        }}
        className="map-marker-aura"
      />
      <Circle
        center={position}
        radius={perimeterRadius}
        pathOptions={{
          color: safeColor,
          fillOpacity: 0,
          weight: 3.2,
          opacity: 0.95,
        }}
        className="map-marker-perimeter"
      />
      <Circle
        center={position}
        radius={waveRadius}
        pathOptions={{
          color: safeColor,
          fillOpacity: 0,
          weight: 2.1,
          opacity: 0.75,
          dashArray: "10 8",
        }}
        className="map-marker-wave"
      />

      <Marker
        ref={markerRef}
        position={position}
        icon={markerIcon}
        eventHandlers={{
          click: onClick,
        }}
      >
        <Popup
          autoPan={autoPan}
          closeButton={true}
          minWidth={240}
          maxWidth={320}
          className="custom-popup map-popup-compact"
          offset={[0, -34]}
        >
          <motion.div
            className="map-popup-card rounded-lg bg-white dark:bg-gray-900 p-3"
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
          >
            <div className="flex items-start justify-between gap-2">
              <h2
                className="map-popup-title text-sm sm:text-base font-semibold text-gray-900 dark:text-gray-100"
                title={name}
              >
                {name}
              </h2>
              <span
                className="inline-flex shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold"
                style={{
                  borderColor: `${safeColor}66`,
                  color: safeColor,
                  backgroundColor: `${safeColor}1A`,
                }}
              >
                {getEmployeesBadge(employees)}
              </span>
            </div>

            <div className="mt-2 flex items-start gap-2 text-gray-700 dark:text-gray-300">
              <FiMapPin className="w-4 h-4 mt-0.5 shrink-0 text-primary-600 dark:text-primary-400" />
              <p className="map-popup-address text-xs sm:text-sm" title={normalizedAddress}>
                {normalizedAddress}
              </p>
            </div>

            <div className="mt-3 rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50/90 dark:bg-gray-800/70 px-2.5 py-2 text-[11px] sm:text-xs">
              <div className="mb-1 inline-flex items-center gap-1 text-gray-500 dark:text-gray-400">
                <FiUsers className="w-3.5 h-3.5" />
                Посещения
              </div>
              <div className="text-sm font-bold" style={{ color: safeColor }}>
                {employees}
              </div>
            </div>
          </motion.div>
        </Popup>
      </Marker>
    </>
  );
};

export default AnimatedMarker;
