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
              fillOpacity: 0.3,
            }}
            className="animate-expand"
          />
          {popupVisible && (
            <Popup position={position} autoPan={false} closeButton={false}>
              <div className="p-4 rounded-xl shadow-xl bg-white text-gray-800 w-70 max-w-full mx-auto">
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
              </div>
            </Popup>
          )}
        </>
      )}
    </>
  );
};

export default AnimatedMarker;
