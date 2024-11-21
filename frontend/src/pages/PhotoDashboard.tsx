import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from "react";
import { PhotoData } from "../schemas/IData";
import { apiUrl } from "../../apiConfig";
import { FaSadTear } from "react-icons/fa";
import { motion, AnimatePresence } from "framer-motion";
import { log } from "../api";
import useWebSocket from "../hooks/useWebSocket";

const PhotoDashboard: React.FC = () => {
  const [photos, setPhotos] = useState<PhotoData[]>([]);
  const [selectedPhoto, setSelectedPhoto] = useState<PhotoData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const maxPhotosRef = useRef<number>(10);
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);
  const gridRef = useRef<HTMLDivElement | null>(null);
  const prevPhotosLengthRef = useRef<number>(0);

  const getCurrentLocalDate = useCallback((): string => {
    const today = new Date();
    const year = today.getFullYear();
    const month = `0${today.getMonth() + 1}`.slice(-2);
    const day = `0${today.getDate()}`.slice(-2);
    return `${year}-${month}-${day}`;
  }, []);

  const date = getCurrentLocalDate();
  log.info("Connecting with date:", date);

  const updateMaxPhotos = useCallback(() => {
    const { innerWidth: width, innerHeight: height } = window;
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

    setPhotos((prev) => prev.slice(0, maxPhotosRef.current));
    log.info("Max photos updated to:", maxPhotosRef.current);

    setFocusedIndex((prevIndex) => {
      if (prevIndex >= maxPhotosRef.current) {
        return maxPhotosRef.current - 1;
      }
      return prevIndex;
    });
  }, []);

  const handleWebSocketMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);
      log.info("WebSocket message received:", data);

      if (data.type === "ping") {
        log.info("Received ping from server.");
        return;
      }

      if (data.photos) {
        log.info("Received photos data.");
        const newPhotos = data.photos.reverse().slice(0, maxPhotosRef.current);
        setPhotos(newPhotos);
        setLoading(false);

        if (prevPhotosLengthRef.current !== newPhotos.length) {
          setFocusedIndex(newPhotos.length > 0 ? 0 : -1);
          prevPhotosLengthRef.current = newPhotos.length;
        }
      } else if (data.newPhoto) {
        log.info("Received new photo data.");
        setPhotos((prev) => {
          const updatedPhotos = [data.newPhoto, ...prev].slice(
            0,
            maxPhotosRef.current
          );
          if (prev.length !== updatedPhotos.length) {
            setFocusedIndex((prevIndex) => (prevIndex === -1 ? 0 : prevIndex));
          }
          prevPhotosLengthRef.current = updatedPhotos.length;
          return updatedPhotos;
        });
      }
    } catch (error) {
      log.error("Error processing WebSocket message:", error);
    }
  }, []);

  const handleOpen = useCallback(() => {
    log.info("WebSocket connection established via hook");
  }, []);

  const handleClose = useCallback((event: CloseEvent) => {
    log.warn("WebSocket connection closed via hook:", event);
  }, []);

  const handleError = useCallback((error: Event) => {
    log.error("WebSocket error via hook:", error);
  }, []);

  const wsUrl = useMemo(() => {
    const protocol = apiUrl.startsWith("https") ? "wss://" : "ws://";
    return `${protocol}${apiUrl.replace(
      /^https?:\/\//,
      ""
    )}/ws/photos/?date=${date}`;
  }, [apiUrl, date]);

  useWebSocket({
    url: wsUrl,
    onMessage: handleWebSocketMessage,
    onOpen: handleOpen,
    onClose: handleClose,
    onError: handleError,
    shouldReconnect: true,
    reconnectInterval: 5000,
    pingInterval: 30000,
    pongTimeout: 10000,
  });

  useEffect(() => {
    updateMaxPhotos();
    window.addEventListener("resize", updateMaxPhotos);

    return () => {
      window.removeEventListener("resize", updateMaxPhotos);
    };
  }, [updateMaxPhotos]);

  useEffect(() => {
    log.info("Photos state updated:", photos);
  }, [photos]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (selectedPhoto) {
        if (e.key === "Escape") {
          setSelectedPhoto(null);
        }
        return;
      }

      if (photos.length === 0) return;

      if (e.key === "ArrowRight") {
        e.preventDefault();
        setFocusedIndex((prevIndex) => {
          const nextIndex = prevIndex + 1;
          return nextIndex >= photos.length ? 0 : nextIndex;
        });
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        setFocusedIndex((prevIndex) => {
          const nextIndex = prevIndex - 1;
          return nextIndex < 0 ? photos.length - 1 : nextIndex;
        });
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (focusedIndex >= 0 && focusedIndex < photos.length) {
          setSelectedPhoto(photos[focusedIndex]);
        }
      }
    },
    [photos, selectedPhoto, focusedIndex]
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [handleKeyDown]);

  useEffect(() => {
    if (focusedIndex >= 0 && focusedIndex < photos.length && gridRef.current) {
      const grid = gridRef.current;
      const photoElements =
        grid.querySelectorAll<HTMLDivElement>(".photo-item");
      const currentPhoto = photoElements[focusedIndex];
      if (currentPhoto) {
        currentPhoto.focus();
      }
    }
  }, [focusedIndex, photos]);

  const gridClasses =
    "grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6";

  const renderLoading = () => (
    <div className="flex flex-col justify-center items-center h-screen text-gray-700">
      <div className="loader w-20 h-20 border-4 border-gray-300 border-t-4 border-t-blue-500 rounded-full animate-spin"></div>
      <motion.p
        className="mt-6 text-xl font-medium text-gray-200"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5 }}
      >
        Загрузка данных, пожалуйста, подождите...
      </motion.p>
    </div>
  );

  const renderNoPhotos = () => (
    <motion.div
      className="flex flex-col justify-center items-center h-screen text-gray-500"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.5 }}
    >
      <FaSadTear className="text-6xl mb-4 " />
      <p className="text-xl">Фотографии отсутствуют</p>
    </motion.div>
  );

  const renderPhotos = () => (
    <div ref={gridRef} className={gridClasses}>
      <AnimatePresence>
        {photos.map((photo, index) => (
          <motion.div
            key={`${photo.photoUrl}-${photo.attendanceTime}`}
            className={`relative bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden cursor-pointer group photo-item focus:outline-none ${
              index === focusedIndex ? "ring-4 neon-glow" : ""
            }`}
            onClick={() => {
              setSelectedPhoto(photo);
              setFocusedIndex(index);
            }}
            role="button"
            tabIndex={0}
            onKeyPress={(e) => {
              if (e.key === "Enter") setSelectedPhoto(photo);
            }}
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -50 }}
            transition={{ duration: 0.5 }}
            whileHover={{ scale: 1.05 }}
            whileFocus={{ scale: 1.05 }}
            aria-label={`Фотография ${photo.staffFullName}`}
          >
            <div className="relative w-full h-60 overflow-hidden">
              <img
                src={`${apiUrl}${photo.photoUrl}`}
                alt={photo.staffFullName}
                className="w-full h-full object-cover transform transition-transform duration-300 group-hover:scale-110"
                loading="lazy"
              />
              <motion.div
                className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent flex items-center justify-center text-white opacity-0 group-hover:opacity-100 transition-opacity duration-300"
                initial={{ opacity: 0 }}
                animate={{ opacity: 0 }}
                whileHover={{ opacity: 1 }}
              >
                <div className="text-center px-2">
                  <h3 className="text-lg font-semibold">
                    {photo.staffFullName}
                  </h3>
                  <p className="text-sm">{photo.department}</p>
                </div>
              </motion.div>
            </div>
            <div className="p-5">
              <h2 className="text-lg font-semibold text-gray-800 dark:text-white truncate">
                {photo.staffFullName}
              </h2>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                {new Date(photo.attendanceTime).toLocaleString()}
              </p>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );

  const renderSelectedPhoto = () =>
    selectedPhoto && (
      <AnimatePresence>
        <motion.div
          className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50"
          onClick={() => setSelectedPhoto(null)}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
        >
          <motion.div
            className="relative bg-white dark:bg-gray-900 rounded-lg overflow-hidden shadow-xl w-11/12 max-w-screen-lg mx-auto"
            onClick={(e) => e.stopPropagation()}
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.8, opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            <button
              className="absolute top-4 right-4 text-gray-800 dark:text-gray-300 hover:text-gray-600 dark:hover:text-white focus:outline-none"
              onClick={() => setSelectedPhoto(null)}
              aria-label="Закрыть"
            >
              ✕
            </button>

            <div className="flex flex-col md:flex-row">
              <div className="w-full md:w-1/2 flex items-center justify-center p-6">
                <img
                  src={`${apiUrl}${selectedPhoto.photoUrl}`}
                  alt={selectedPhoto.staffFullName}
                  className="max-w-full max-h-full object-contain transform transition-transform duration-300 hover:scale-105"
                />
              </div>
              <div className="w-full md:w-1/2 p-8 flex flex-col justify-center">
                <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-4">
                  {selectedPhoto.staffFullName}
                </h2>
                <p className="text-lg text-gray-600 dark:text-gray-300 mb-2">
                  <strong>Отдел:</strong> {selectedPhoto.department}
                </p>
                <p className="text-lg text-gray-600 dark:text-gray-300 mb-2">
                  <strong>Время:</strong>{" "}
                  {new Date(selectedPhoto.attendanceTime).toLocaleString()}
                </p>
                {selectedPhoto.tutorInfo && (
                  <p className="text-md text-gray-500 dark:text-gray-400 mt-2">
                    {selectedPhoto.tutorInfo}
                  </p>
                )}
              </div>
            </div>
          </motion.div>
        </motion.div>
      </AnimatePresence>
    );

  return (
    <div className="min-h-screen p-6 bg-transparent">
      {loading
        ? renderLoading()
        : photos.length === 0
        ? renderNoPhotos()
        : renderPhotos()}

      {renderSelectedPhoto()}
    </div>
  );
};

export default PhotoDashboard;
