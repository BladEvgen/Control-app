import React, { useEffect, useRef } from "react";
import { Marker, Circle, Popup } from "react-leaflet";
import L from "leaflet";
import { FaMapMarkerAlt, FaUsers } from "react-icons/fa";
import { motion } from "framer-motion";

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

  const getScaleFactor = (zoom: number): number => {
    const baseZoom = 13.5;
    const scale = 1 + (zoom - baseZoom) * 0.1;
    return Math.max(0.5, Math.min(scale, 2));
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
      })
    : null;

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

  return (
    <>
      {isVisible && (
        <>
          <Marker
            ref={markerRef}
            position={position}
            icon={scaledCustomIcon || undefined}
            eventHandlers={{
              click: onClick,
            }}
          >
            <Popup autoPan={false} closeButton={false}>
              <motion.div
                className="p-4 rounded-xl shadow-xl bg-white text-gray-800 w-72 max-w-full mx-auto"
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                transition={{ duration: 0.3 }}
              >
                <h2 className="text-xl font-bold text-gray-900 mb-1 leading-tight">
                  {name}
                </h2>
                <div className="flex items-center mb-3">
                  <FaMapMarkerAlt className="text-blue-500 text-lg mr-2" />
                  <p className="text-base text-gray-700 break-words hyphens-auto">
                    {address}
                  </p>
                </div>
                <div className="flex items-center justify-start space-x-3">
                  <FaUsers className="text-green-500 text-lg" />
                  <p className="text-base font-medium text-gray-700">
                    Посещения:{" "}
                    <span className="font-semibold">{employees}</span>
                  </p>
                </div>
              </motion.div>
            </Popup>
          </Marker>

          <Circle
            center={position}
            radius={radius}
            pathOptions={{
              color: color,
              fillColor: color,
              fillOpacity: 0.3,
            }}
            className="animated-circle"
          />
        </>
      )}
    </>
  );
};

export default AnimatedMarker;
