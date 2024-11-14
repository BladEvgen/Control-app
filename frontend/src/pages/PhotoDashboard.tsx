import React, { useState, useEffect, useRef } from "react";
import { PhotoData } from "../schemas/IData";
import { apiUrl } from "../../apiConfig";

const PhotoDashboard: React.FC = () => {
  const [photos, setPhotos] = useState<PhotoData[]>([]);
  const [selectedPhoto, setSelectedPhoto] = useState<PhotoData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const maxPhotosRef = useRef<number>(10);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const updateMaxPhotos = () => {
    const width = window.innerWidth;
    const height = window.innerHeight;
    const aspectRatio = width / height;

    const isMobile = /Mobi|Android/i.test(navigator.userAgent);
    const isTablet = /Tablet|iPad/i.test(navigator.userAgent);

    if (isMobile) {
      maxPhotosRef.current = 7;
    } else if (isTablet) {
      maxPhotosRef.current = 10;
    } else if (aspectRatio > 2) {
      maxPhotosRef.current = 20;
    } else if (width >= 3840) {
      maxPhotosRef.current = 25;
    } else if (width >= 2560) {
      maxPhotosRef.current = 15;
    } else if (width >= 1920) {
      maxPhotosRef.current = 12;
    } else {
      maxPhotosRef.current = 10;
    }
  };

  const createWebSocketConnection = () => {
    let wsScheme = apiUrl.startsWith("https") ? "wss" : "ws";
    const apiHost = apiUrl.replace(/^https?:\/\//, "");

    const today = new Date();
    const date = new Date(today.getTime() - today.getTimezoneOffset() * 60000)
      .toISOString()
      .split("T")[0];

    const wsUrl = `${wsScheme}://${apiHost}/ws/photos/?date=${date}`;

    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => {
      console.log("WebSocket connection established");
      if (reconnectTimeoutRef.current !== null) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    wsRef.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "ping") {
        return;
      }
      if (data.photos) {
        setPhotos(data.photos.reverse().slice(0, maxPhotosRef.current));
        setLoading(false);
      } else if (data.newPhoto) {
        setPhotos((prev) =>
          [data.newPhoto, ...prev].slice(0, maxPhotosRef.current)
        );
      }
    };

    wsRef.current.onclose = (event) => {
      console.log("WebSocket connection closed:", event);
      if (reconnectTimeoutRef.current === null) {
        reconnectTimeoutRef.current = window.setTimeout(() => {
          console.log("Reconnecting to WebSocket...");
          createWebSocketConnection();
        }, 5000);
      }
    };

    wsRef.current.onerror = (error) => {
      console.error("WebSocket error:", error);
      wsRef.current?.close();
    };
  };

  useEffect(() => {
    updateMaxPhotos();
    window.addEventListener("resize", updateMaxPhotos);

    createWebSocketConnection();

    return () => {
      window.removeEventListener("resize", updateMaxPhotos);
      wsRef.current?.close();
      if (reconnectTimeoutRef.current !== null) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, []);

  return (
    <div className="min-h-screen p-4">
      {loading ? (
        <div className="flex flex-col justify-center items-center h-screen text-gray-700">
          <div className="loader w-16 h-16 border-4 border-gray-300 border-t-4 border-t-blue-500 rounded-full animate-spin"></div>
          <p className="mt-4 text-lg font-medium text-white">
            Загрузка данных, пожалуйста, подождите...
          </p>
        </div>
      ) : (
        <div className="grid gap-6 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {photos.map((photo, index) => (
            <div
              key={index}
              className="relative bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden cursor-pointer group transition-all duration-300 hover:shadow-xl"
              onClick={() => setSelectedPhoto(photo)}
            >
              <div className="relative w-full h-56 overflow-hidden">
                <img
                  src={`${apiUrl}${photo.photoUrl}`}
                  alt={photo.staffFullName}
                  className="w-full h-full object-cover transform group-hover:scale-105 transition-transform duration-300"
                />
              </div>
              <div className="p-4">
                <h2 className="text-lg font-semibold text-gray-800 dark:text-white truncate">
                  {photo.staffFullName}
                </h2>
                <p className="text-sm text-gray-600 dark:text-gray-300 truncate">
                  {photo.department}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {new Date(photo.attendanceTime).toLocaleString()}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {selectedPhoto && (
        <div
          className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50"
          onClick={() => setSelectedPhoto(null)}
        >
          <div
            className="relative bg-white dark:bg-gray-900 rounded-lg overflow-hidden shadow-xl w-11/12 max-w-screen-md mx-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="absolute top-4 right-4 text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-white"
              onClick={() => setSelectedPhoto(null)}
            >
              ✕
            </button>

            <div className="flex flex-col md:flex-row">
              <div className="w-full md:w-1/2 flex items-center justify-center p-4">
                <img
                  src={`${apiUrl}${selectedPhoto.photoUrl}`}
                  alt={selectedPhoto.staffFullName}
                  className="max-w-full max-h-full object-contain"
                />
              </div>
              <div className="w-full md:w-1/2 p-6 flex flex-col justify-center">
                <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-4">
                  {selectedPhoto.staffFullName}
                </h2>
                <p className="text-lg text-gray-600 dark:text-gray-300 mb-2">
                  Отдел: {selectedPhoto.department}
                </p>
                <p className="text-lg text-gray-600 dark:text-gray-300 mb-2">
                  Время:{" "}
                  {new Date(selectedPhoto.attendanceTime).toLocaleString()}
                </p>
                {selectedPhoto.tutorInfo && (
                  <p className="text-md text-gray-500 dark:text-gray-400 mt-2">
                    {selectedPhoto.tutorInfo}
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PhotoDashboard;
