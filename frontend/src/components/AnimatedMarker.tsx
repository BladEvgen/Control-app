import React, { useEffect, useRef } from "react";
import { Marker, Circle, Popup } from "react-leaflet";
import L from "leaflet";

interface AnimatedMarkerProps {
  position: [number, number];
  name: string;
  employees: number;
  isVisible: boolean;
  icon: L.Icon;
  onClick: () => void;
  popupVisible: boolean;
  theme: string;
  radius: number;
  color: string;
}

const AnimatedMarker: React.FC<AnimatedMarkerProps> = ({
  position,
  name,
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
              <div className="p-2 text-center">
                <h2 className="font-bold text-sm text-gray-800 ">{name}</h2>
                <p className="text-xs text-gray-600 ">
                  Сотрудников: {employees}
                </p>
              </div>
            </Popup>
          )}
        </>
      )}
    </>
  );
};

export default AnimatedMarker;
