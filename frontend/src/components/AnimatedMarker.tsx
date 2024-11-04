import React, { useEffect, useRef } from "react";
import { Marker, Circle, Popup } from "react-leaflet";
import L from "leaflet";
import { FaMapMarkerAlt, FaUsers } from "react-icons/fa";

interface AnimatedMarkerProps {
  position: [number, number];
  name: string;
  address: string;
  employees: number;
  isVisible: boolean;
  icon: L.Icon;
  onClick: () => void;
  popupVisible: boolean;
  radius: number;
  color: string;
}

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
}) => {
  const markerRef = useRef<L.Marker | null>(null);

  useEffect(() => {
    if (markerRef.current && isVisible) {
      const markerElement = markerRef.current.getElement();
      if (markerElement) {
        markerElement.style.opacity = "0";
        setTimeout(() => {
          markerElement.style.opacity = "1";
          markerElement.classList.add("animate-drop");
        }, 500);
      }
    }
  }, [isVisible]);

  return (
    <>
      {isVisible && (
        <>
          <Marker
            ref={markerRef}
            position={position}
            icon={icon}
            eventHandlers={{
              click: onClick,
            }}
          />
          <Circle
            center={position}
            radius={radius}
            pathOptions={{
              color: color,
              fillColor: color,
              fillOpacity: 0.7,
            }}
            className="animate-expand"
          />
          {popupVisible && (
            <Popup position={position} autoPan={false} closeButton={false}>
              <div
                className="p-3 rounded-lg shadow-lg bg-white text-gray-800 w-72 max-w-full mx-auto text-center"
                style={{
                  minWidth: "250px",
                  maxWidth: "320px",
                }}
              >
                <h2 className="text-lg font-semibold truncate">{name}</h2>
                <div className="flex items-center justify-center mt-1 space-x-2">
                  <FaMapMarkerAlt className="text-blue-500 text-base" />
                  <p className="text-sm truncate">{address}</p>
                </div>
                <div className="flex items-center justify-center mt-1 space-x-2">
                  <FaUsers className="text-green-500 text-base" />
                  <p className="text-sm truncate">Посещения: {employees}</p>
                </div>
              </div>
            </Popup>
          )}
        </>
      )}
    </>
  );
};

export default AnimatedMarker;
