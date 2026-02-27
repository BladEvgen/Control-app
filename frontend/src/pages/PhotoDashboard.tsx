import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  FaExpand,
  FaCompress,
  FaTimes,
  FaImage,
  FaClock,
  FaBuilding,
  FaRegCalendarAlt,
} from "react-icons/fa";
import { PhotoData } from "../schemas/IData";
import { apiUrl } from "../../apiConfig";
import { motion, AnimatePresence } from "framer-motion";
import { log } from "../api";
import useWebSocket from "../hooks/useWebSocket";
import LoaderComponent from "../components/LoaderComponent";

const PING_INTERVAL = 15000;
const PONG_TIMEOUT = 8000;
const MARQUEE_SPEED = 95;
const MARQUEE_HOVER_SPEED = 0;
const SMOOTH_TAU = 0.25;
const MIN_TRACK_COPIES = 2;
const TRACK_COPY_HEADROOM = 2;

const getLabelForDepartment = (photo: PhotoData): string =>
  photo.tutorInfo ? "Группа/Предмет" : "Отдел";

const formatTime = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

const CARD_WIDTH_BASE = 220;
const CARD_WIDTH_SM = 260;
const CARD_WIDTH_MD = 280;
const CARD_WIDTH_LG = 300;
const CARD_META_HEIGHT = 100;
const ROW_GAP_PX = 12;
const HEADER_ESTIMATE_PX = 200;
const BOTTOM_RESERVE_KIOSK_PX = 88;
const KIOSK_HEADER_RESERVE_PX = 200;
const KIOSK_MAIN_TOP_RESERVE_PX = 100;
const CARD_WIDTH_MIN_PX = 140;
const KIOSK_SHRINK_VIEWPORT_WIDTH = 1280;
const TAPE_NUM_ROWS_MIN = 1;
const TAPE_NUM_ROWS_MAX = 6;

const getCardWidthForViewport = (viewportWidth: number): number => {
  if (viewportWidth >= 1024) return CARD_WIDTH_LG;
  if (viewportWidth >= 768) return CARD_WIDTH_MD;
  if (viewportWidth >= 640) return CARD_WIDTH_SM;
  return CARD_WIDTH_BASE;
};

const getTapeNumRows = (
  viewportHeight: number,
  viewportWidth: number,
  extraBottomReservePx = 0,
  extraTopReservePx = 0,
  headerReservePx?: number,
): number => {
  const header = headerReservePx ?? HEADER_ESTIMATE_PX;
  const cardW = getCardWidthForViewport(viewportWidth);
  const rowHeight = cardW + CARD_META_HEIGHT + ROW_GAP_PX;
  const available = Math.max(
    100,
    viewportHeight - header - extraBottomReservePx - extraTopReservePx,
  );
  const n = Math.floor(available / rowHeight);
  return Math.max(TAPE_NUM_ROWS_MIN, Math.min(TAPE_NUM_ROWS_MAX, n));
};

const MarqueeTrack: React.FC<{
  items: (PhotoData | null)[];
  rowIndex: number;
  speedPxSec: number;
  hoverSpeed?: number;
  isPaused: boolean;
  cardWidthPx: number;
  renderItem: (
    photo: PhotoData | null,
    displayIndex: number,
    copyIndex: number,
  ) => React.ReactNode;
}> = ({
  items,
  rowIndex,
  speedPxSec,
  hoverSpeed = MARQUEE_HOVER_SPEED,
  isPaused,
  cardWidthPx,
  renderItem,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const seqRef = useRef<HTMLUListElement>(null);

  const [seqWidth, setSeqWidth] = useState(0);
  const [copyCount, setCopyCount] = useState(MIN_TRACK_COPIES);

  const offsetRef = useRef(0);
  const velocityRef = useRef(0);
  const lastTimestampRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);

  const updateDimensions = useCallback(() => {
    const containerWidth = containerRef.current?.clientWidth ?? 0;
    const sequenceWidth = seqRef.current?.getBoundingClientRect().width ?? 0;
    if (sequenceWidth <= 0) return;

    const roundedSequenceWidth = Math.ceil(sequenceWidth);
    setSeqWidth(roundedSequenceWidth);

    const copiesNeeded =
      Math.ceil(containerWidth / roundedSequenceWidth) + TRACK_COPY_HEADROOM;
    setCopyCount(Math.max(MIN_TRACK_COPIES, copiesNeeded));
  }, []);

  useEffect(() => {
    updateDimensions();
  }, [updateDimensions, items, rowIndex]);

  useEffect(() => {
    if (!window.ResizeObserver) {
      window.addEventListener("resize", updateDimensions);
      return () => window.removeEventListener("resize", updateDimensions);
    }

    const ro = new ResizeObserver(updateDimensions);
    if (containerRef.current) ro.observe(containerRef.current);
    if (seqRef.current) ro.observe(seqRef.current);

    return () => ro.disconnect();
  }, [updateDimensions]);

  useEffect(() => {
    const images = seqRef.current?.querySelectorAll("img") ?? [];
    if (images.length === 0) {
      updateDimensions();
      return;
    }

    let remaining = images.length;
    const handleImage = () => {
      remaining -= 1;
      if (remaining <= 0) {
        updateDimensions();
      }
    };

    images.forEach((img) => {
      const htmlImg = img as HTMLImageElement;
      if (htmlImg.complete) {
        handleImage();
      } else {
        htmlImg.addEventListener("load", handleImage, { once: true });
        htmlImg.addEventListener("error", handleImage, { once: true });
      }
    });

    return () => {
      images.forEach((img) => {
        img.removeEventListener("load", handleImage);
        img.removeEventListener("error", handleImage);
      });
    };
  }, [items, updateDimensions]);

  useEffect(() => {
    const track = trackRef.current;
    if (!track || seqWidth <= 0) return;

    offsetRef.current = ((offsetRef.current % seqWidth) + seqWidth) % seqWidth;
    track.style.transform = `translate3d(-${offsetRef.current}px, 0, 0)`;

    const animate = (timestamp: number) => {
      if (lastTimestampRef.current === null) {
        lastTimestampRef.current = timestamp;
      }

      const dt = Math.max(0, timestamp - lastTimestampRef.current) / 1000;
      lastTimestampRef.current = timestamp;

      const targetVelocity = isPaused ? hoverSpeed : speedPxSec;
      const easingFactor = 1 - Math.exp(-dt / SMOOTH_TAU);
      velocityRef.current +=
        (targetVelocity - velocityRef.current) * easingFactor;

      let nextOffset = offsetRef.current + velocityRef.current * dt;
      nextOffset = ((nextOffset % seqWidth) + seqWidth) % seqWidth;
      offsetRef.current = nextOffset;

      track.style.transform = `translate3d(-${nextOffset}px, 0, 0)`;
      rafRef.current = requestAnimationFrame(animate);
    };

    rafRef.current = requestAnimationFrame(animate);
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      lastTimestampRef.current = null;
    };
  }, [seqWidth, speedPxSec, hoverSpeed, isPaused]);

  return (
    <div
      ref={containerRef}
      className="relative overflow-x-hidden overflow-y-visible"
    >
      <div
        ref={trackRef}
        className={`flex w-max will-change-transform ${isPaused ? "photo-marquee-paused" : ""}`}
      >
        {Array.from({ length: copyCount }, (_, copyIndex) => (
          <ul
            key={`row-${rowIndex}-copy-${copyIndex}`}
            ref={copyIndex === 0 ? seqRef : undefined}
            className="flex items-center"
            aria-hidden={copyIndex > 0}
          >
            {items.map((photo, itemIndex) => {
              const displayIndex = copyIndex * items.length + itemIndex;
              const key =
                photo != null
                  ? `row-${rowIndex}-${copyIndex}-${photo.photoUrl}-${photo.attendanceTime}-${itemIndex}`
                  : `row-${rowIndex}-${copyIndex}-empty-${itemIndex}`;
              return (
                <li
                  key={key}
                  className="mr-4 my-1 flex-shrink-0 list-none"
                  style={photo == null ? { width: cardWidthPx } : undefined}
                >
                  {renderItem(photo, displayIndex, copyIndex)}
                </li>
              );
            })}
          </ul>
        ))}
      </div>
    </div>
  );
};

interface DocumentWithFullscreen extends Document {
  webkitExitFullscreen?: () => Promise<void> | void;
  mozCancelFullScreen?: () => Promise<void> | void;
  msExitFullscreen?: () => Promise<void> | void;
  webkitFullscreenElement?: Element | null;
  mozFullScreenElement?: Element | null;
  msFullscreenElement?: Element | null;
}

interface DocumentElementWithFullscreen extends HTMLElement {
  webkitRequestFullscreen?: () => Promise<void> | void;
  mozRequestFullScreen?: () => Promise<void> | void;
  msRequestFullscreen?: () => Promise<void> | void;
}

const PhotoDashboard: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const isKiosk =
    /\/photo$/.test(location.pathname) &&
    new URLSearchParams(location.search).get("kiosk") === "1";

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isFullscreenBusy, setIsFullscreenBusy] = useState(false);
  const [photos, setPhotos] = useState<PhotoData[]>([]);
  const [selectedPhoto, setSelectedPhoto] = useState<PhotoData | null>(null);
  const selectedPhotoRef = useRef<PhotoData | null>(null);
  const keepKioskOnFullscreenExitRef = useRef(false);
  const fullscreenToggleLockRef = useRef(false);

  const getFullscreenElement = useCallback((): Element | null => {
    const doc = document as DocumentWithFullscreen;
    return (
      document.fullscreenElement ??
      doc.webkitFullscreenElement ??
      doc.mozFullScreenElement ??
      doc.msFullscreenElement ??
      null
    );
  }, []);

  useEffect(() => {
    selectedPhotoRef.current = selectedPhoto;
  }, [selectedPhoto]);

  const handleFullscreenChange = useCallback(() => {
    const newState = !!getFullscreenElement();
    setIsFullscreen(newState);
    setIsFullscreenBusy(false);
    fullscreenToggleLockRef.current = false;
    if (!newState) {
      const keepKiosk =
        keepKioskOnFullscreenExitRef.current || !!selectedPhotoRef.current;
      keepKioskOnFullscreenExitRef.current = false;
      setSelectedPhoto(null);
      if (
        !keepKiosk &&
        new URLSearchParams(window.location.search).get("kiosk") === "1"
      ) {
        navigate(
          { pathname: location.pathname, search: "" },
          { replace: true },
        );
      }
    }
  }, [navigate, location.pathname, getFullscreenElement]);

  useEffect(() => {
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    document.addEventListener("webkitfullscreenchange", handleFullscreenChange);
    document.addEventListener("mozfullscreenchange", handleFullscreenChange);
    document.addEventListener("MSFullscreenChange", handleFullscreenChange);
    handleFullscreenChange();
    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
      document.removeEventListener(
        "webkitfullscreenchange",
        handleFullscreenChange,
      );
      document.removeEventListener(
        "mozfullscreenchange",
        handleFullscreenChange,
      );
      document.removeEventListener(
        "MSFullscreenChange",
        handleFullscreenChange,
      );
    };
  }, [handleFullscreenChange]);

  const handleFullscreenToggle = useCallback(async () => {
    if (fullscreenToggleLockRef.current) return;
    const docEl = document.documentElement as DocumentElementWithFullscreen;
    const doc = document as DocumentWithFullscreen;
    const currentlyFullscreen = !!getFullscreenElement();

    fullscreenToggleLockRef.current = true;
    setIsFullscreenBusy(true);

    try {
      if (!currentlyFullscreen) {
        if (!isKiosk) {
          navigate(
            { pathname: location.pathname, search: "?kiosk=1" },
            { replace: true },
          );
        }
        await new Promise<void>((resolve) =>
          window.setTimeout(resolve, isKiosk ? 0 : 120),
        );
        const req =
          docEl.requestFullscreen ??
          docEl.webkitRequestFullscreen ??
          docEl.mozRequestFullScreen ??
          docEl.msRequestFullscreen;
        if (req) {
          await Promise.resolve(req.call(docEl));
        }
      } else {
        keepKioskOnFullscreenExitRef.current = false;
        const exit =
          document.exitFullscreen ??
          doc.webkitExitFullscreen ??
          doc.mozCancelFullScreen ??
          doc.msExitFullscreen;
        if (exit) {
          await Promise.resolve(exit.call(doc));
          if (getFullscreenElement()) {
            await new Promise<void>((resolve) =>
              window.setTimeout(resolve, 140),
            );
            await Promise.resolve(exit.call(doc));
          }
        }
      }
    } catch (error) {
      log.warn("Fullscreen toggle failed:", error);
    } finally {
      window.setTimeout(() => {
        if (!getFullscreenElement()) {
          setIsFullscreenBusy(false);
          fullscreenToggleLockRef.current = false;
        }
      }, 360);
    }
  }, [isKiosk, navigate, location.pathname, getFullscreenElement]);

  const todayLabel = new Date().toLocaleDateString("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  const pageTitle = isFullscreen
    ? "Лента фотографий посещаемости"
    : "Фотографии посещаемости";

  const pageSubtitle = isFullscreen
    ? "Режим показа в реальном времени"
    : "Актуальные отметки за текущий день";

  const [loading, setLoading] = useState<boolean>(true);
  const maxPhotosRef = useRef<number>(12);
  const [hoveredCardKey, setHoveredCardKey] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [cardWidthPx, setCardWidthPx] = useState<number>(CARD_WIDTH_MD);
  const [tapeNumRows, setTapeNumRows] = useState<number>(3);
  const [kioskNarrowViewport, setKioskNarrowViewport] =
    useState<boolean>(false);

  const getCurrentLocalDate = useCallback((): string => {
    const today = new Date();
    const year = today.getFullYear();
    const month = `0${today.getMonth() + 1}`.slice(-2);
    const day = `0${today.getDate()}`.slice(-2);
    return `${year}-${month}-${day}`;
  }, []);

  const date = getCurrentLocalDate();
  log.info("Connecting with date:", date);

  const getMaxPhotos = useCallback(() => {
    const { innerWidth: w, innerHeight: h } = window;
    const aspect = w / h;
    const ua = navigator.userAgent;
    const isMobile = /Mobi|Android/i.test(ua);
    const isTablet = /Tablet|iPad/i.test(ua);

    let max: number;
    if (isMobile) {
      max = aspect > 1 ? 6 : 4;
    } else if (isTablet) {
      max = aspect > 1 ? 10 : 6;
    } else if (aspect > 2.2) {
      max = 28;
    } else if (aspect > 1.8) {
      max = 22;
    } else if (w >= 3840) {
      max = 24;
    } else if (w >= 2560) {
      max = 18;
    } else if (w >= 1920) {
      max = 14;
    } else if (w >= 1280) {
      max = 10;
    } else if (w >= 768) {
      max = 8;
    } else {
      max = 6;
    }
    return isKiosk ? Math.min(max * 2, 48) : max;
  }, [isKiosk]);

  const updateMaxPhotos = useCallback(() => {
    maxPhotosRef.current = getMaxPhotos();
    setPhotos((prev) => prev.slice(0, maxPhotosRef.current));
  }, [getMaxPhotos]);

  const handleWebSocketMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "ping" || data.type === "heartbeat") return;

      if (data.photos) {
        const newPhotos = [...data.photos]
          .reverse()
          .slice(0, maxPhotosRef.current);
        setPhotos(newPhotos);
        setLoading(false);
      } else if (data.newPhoto) {
        setPhotos((prev) =>
          [data.newPhoto, ...prev].slice(0, maxPhotosRef.current),
        );
      }
    } catch (error) {
      log.error("Error processing WebSocket message:", error);
    }
  }, []);

  const wsUrl = useMemo(() => {
    const urlObj = new URL(apiUrl);
    const protocol = urlObj.protocol === "https:" ? "wss" : "ws";
    return `${protocol}://${urlObj.host}/ws/photos/?date=${date}`;
  }, [date]);

  const { isConnected, reconnect } = useWebSocket({
    url: wsUrl,
    onMessage: handleWebSocketMessage,
    onOpen: useCallback(() => log.info("WebSocket connected"), []),
    onClose: useCallback(
      (e: CloseEvent) => log.warn("WebSocket closed:", e),
      [],
    ),
    onError: useCallback((e: Event) => log.error("WebSocket error:", e), []),
    shouldReconnect: true,
    reconnectInterval: 3000,
    pingInterval: PING_INTERVAL,
    pongTimeout: PONG_TIMEOUT,
  });

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible" && !isConnected) {
        reconnect();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [isConnected, reconnect]);

  useEffect(() => {
    updateMaxPhotos();
    window.addEventListener("resize", updateMaxPhotos);
    return () => window.removeEventListener("resize", updateMaxPhotos);
  }, [updateMaxPhotos]);

  useEffect(() => {
    const getViewportSize = (): { w: number; h: number } => {
      const vv = window.visualViewport;
      const h = vv ? vv.height : window.innerHeight;
      const w = vv ? vv.width : window.innerWidth;
      return { w, h };
    };
    const updateLayout = () => {
      const { w, h } = getViewportSize();
      const isKioskMode = isKiosk || isFullscreen;
      const extraBottom = isKioskMode ? BOTTOM_RESERVE_KIOSK_PX : 0;
      const extraTop = isKioskMode ? KIOSK_MAIN_TOP_RESERVE_PX : 0;
      const headerReserve = isKioskMode ? KIOSK_HEADER_RESERVE_PX : undefined;
      const availableHeight = Math.max(
        0,
        h - (headerReserve ?? HEADER_ESTIMATE_PX) - extraBottom - extraTop,
      );

      let cardW = getCardWidthForViewport(w);
      const narrowViewport = w < KIOSK_SHRINK_VIEWPORT_WIDTH;
      if (isKioskMode && narrowViewport) {
        cardW = Math.round(cardW * 0.9);
      }

      const rows = getTapeNumRows(h, w, extraBottom, extraTop, headerReserve);
      setTapeNumRows(rows);

      let heightCapped = false;
      const rowHeight = cardW + CARD_META_HEIGHT + ROW_GAP_PX;
      if (isKioskMode && rows > 0 && availableHeight < rows * rowHeight) {
        const maxCardH =
          Math.floor(availableHeight / rows) - CARD_META_HEIGHT - ROW_GAP_PX;
        cardW = Math.max(CARD_WIDTH_MIN_PX, Math.min(cardW, maxCardH));
        heightCapped = true;
      }
      setCardWidthPx(cardW);
      setKioskNarrowViewport(isKioskMode && (narrowViewport || heightCapped));
    };
    updateLayout();
    const el = containerRef.current;
    const ro = new ResizeObserver(updateLayout);
    if (el) ro.observe(el);
    window.addEventListener("resize", updateLayout);
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", updateLayout);
      window.visualViewport.addEventListener("scroll", updateLayout);
    }
    document.addEventListener("fullscreenchange", updateLayout);
    document.addEventListener("webkitfullscreenchange", updateLayout);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", updateLayout);
      if (window.visualViewport) {
        window.visualViewport.removeEventListener("resize", updateLayout);
        window.visualViewport.removeEventListener("scroll", updateLayout);
      }
      document.removeEventListener("fullscreenchange", updateLayout);
      document.removeEventListener("webkitfullscreenchange", updateLayout);
    };
  }, [isKiosk, isFullscreen]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" || e.key === "Backspace") {
        if (selectedPhoto) {
          e.preventDefault();
          e.stopPropagation();
          if ("stopImmediatePropagation" in e) e.stopImmediatePropagation();
          keepKioskOnFullscreenExitRef.current = isKiosk;
          setSelectedPhoto(null);
          return;
        }
      }
      if (e.key === "F11") {
        e.preventDefault();
        handleFullscreenToggle();
      }
    },
    [selectedPhoto, handleFullscreenToggle, isKiosk],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, [handleKeyDown]);

  useEffect(() => {
    if (selectedPhoto) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [selectedPhoto]);

  const getHints = useCallback(() => {
    if (typeof window === "undefined") return "";
    const hasTouch = navigator.maxTouchPoints > 0 || "ontouchstart" in window;
    const hasFinePointer = window.matchMedia(
      "(hover: hover) and (pointer: fine)",
    ).matches;

    if (hasTouch && !hasFinePointer) {
      return "Коснитесь фото, чтобы открыть карточку";
    }
    if (hasTouch && hasFinePointer) {
      return "Клик или касание по фото · Esc — закрыть";
    }
    return "Клик по фото · Esc — закрыть";
  }, []);

  const [hints, setHints] = useState("");

  useEffect(() => {
    setHints(getHints());
    const onResize = () => setHints(getHints());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [getHints]);

  const renderLoading = () => (
    <div className="flex flex-col justify-center items-center py-24 text-gray-700 dark:text-gray-300">
      <LoaderComponent />
      <p className="mt-6 text-lg animate-pulse">Загрузка посещаемости...</p>
    </div>
  );

  const renderNoPhotos = () => (
    <motion.div
      className="py-16 sm:py-20"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.45 }}
    >
      <div className="mx-auto w-full max-w-2xl rounded-3xl border border-white/60 dark:border-gray-700/70 bg-white/65 dark:bg-gray-900/50 backdrop-blur-md shadow-xl p-8 sm:p-10">
        <div className="mx-auto mb-5 w-16 h-16 rounded-2xl bg-gradient-to-br from-primary-500 to-secondary-500 text-white flex items-center justify-center shadow-lg">
          <FaImage className="w-7 h-7" />
        </div>
        <h2 className="text-center text-2xl font-semibold text-gray-800 dark:text-gray-100">
          Пока нет фотографий
        </h2>
        <p className="mt-2 text-center text-sm sm:text-base text-gray-600 dark:text-gray-300">
          Карточки сотрудников и студентов появятся здесь после отметки
          посещаемости.
        </p>
        <p className="mt-3 text-center text-xs sm:text-sm text-gray-500 dark:text-gray-400">
          Оставьте страницу открытой: обновление происходит автоматически.
        </p>
      </div>
    </motion.div>
  );

  const photoRows = useMemo(() => {
    const numRows = tapeNumRows;
    if (numRows <= 0 || photos.length === 0) {
      return [];
    }
    const perRow = Math.ceil(photos.length / numRows);
    const rows: (PhotoData | null)[][] = [];
    for (let r = 0; r < numRows; r++) {
      const start = r * perRow;
      const end = Math.min(start + perRow, photos.length);
      if (start < end) {
        rows.push(photos.slice(start, end));
      }
    }
    return rows;
  }, [photos, tapeNumRows]);

  const tapeCols = Math.ceil(photos.length / tapeNumRows) || 1;
  const marqueeSpeed = useMemo(
    () => MARQUEE_SPEED + Math.min(Math.max(tapeCols, 1), 10) * 2,
    [tapeCols],
  );

  const renderCardMeta = useCallback((photo: PhotoData) => {
    return (
      <div className="p-3.5 space-y-1.5">
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100 truncate">
          {photo.staffFullName}
        </h2>
        <p className="text-xs text-gray-600 dark:text-gray-300 flex items-center gap-1.5 min-w-0">
          <FaBuilding className="w-3 h-3 opacity-75 shrink-0" />
          <span className="truncate">{photo.department}</span>
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
          <FaClock className="w-3 h-3 opacity-75 shrink-0" />
          <span>{formatTime(photo.attendanceTime)}</span>
        </p>
      </div>
    );
  }, []);

  const renderPhotoCard = useCallback(
    (
      photo: PhotoData,
      keyIndex: number,
      rowIndex: number,
      cardIndex: number,
      isHovered: boolean,
      kioskCardWidth?: number,
    ) => (
      <motion.article
        key={`${photo.photoUrl}-${photo.attendanceTime}-${keyIndex}`}
        initial={false}
        className={`photo-item group relative flex-shrink-0 w-[220px] sm:w-[260px] md:w-[280px] lg:w-[300px] rounded-2xl md:rounded-3xl cursor-pointer select-none focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/60 focus-visible:ring-offset-2 flex flex-col transition-all duration-300 ${
          isHovered
            ? ""
            : "overflow-hidden bg-white/95 dark:bg-gray-800/95 ring-1 ring-white/80 dark:ring-gray-700/90 shadow-[0_12px_30px_-20px_rgba(15,23,42,0.7)] hover:shadow-[0_20px_45px_-25px_rgba(37,99,235,0.55)] hover:ring-primary-300/70 dark:hover:ring-primary-400/45"
        }`}
        style={kioskCardWidth != null ? { width: kioskCardWidth } : undefined}
        onClick={() => setSelectedPhoto(photo)}
        onMouseEnter={() => setHoveredCardKey(`r${rowIndex}-i${cardIndex}`)}
        onMouseLeave={() => setHoveredCardKey(null)}
        onTouchStart={() => setHoveredCardKey(`r${rowIndex}-i${cardIndex}`)}
        onTouchEnd={() => setHoveredCardKey(null)}
        role="button"
        tabIndex={0}
        aria-label={`${photo.staffFullName}, ${photo.department}`}
        whileHover={{ y: -4 }}
        whileTap={{ scale: 0.98 }}
      >
        {isHovered ? (
          <div className="photo-electric-border w-full flex-1 flex flex-col min-h-0 rounded-2xl">
            <div className="photo-electric-border-inner flex flex-col flex-1 overflow-hidden rounded-2xl relative">
              <div className="photo-shine-overlay" aria-hidden />
              <div className="relative w-full aspect-square flex items-center justify-center overflow-hidden bg-gradient-to-br from-gray-100 via-white to-gray-200 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
                <img
                  src={`${apiUrl}${photo.photoUrl}`}
                  alt={photo.staffFullName}
                  className="w-full h-full object-contain transition-opacity duration-300"
                  loading="lazy"
                  draggable={false}
                />
              </div>
              {renderCardMeta(photo)}
            </div>
          </div>
        ) : (
          <>
            <div className="relative w-full aspect-square flex items-center justify-center overflow-hidden bg-gradient-to-br from-gray-100 via-white to-gray-200 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
              <img
                src={`${apiUrl}${photo.photoUrl}`}
                alt={photo.staffFullName}
                className="w-full h-full object-contain transition-opacity duration-300"
                loading="lazy"
                draggable={false}
              />
            </div>
            {renderCardMeta(photo)}
          </>
        )}
      </motion.article>
    ),
    [renderCardMeta],
  );

  const renderPhotos = () => (
    <div
      className={
        isKiosk
          ? "min-h-[100vh] min-h-[100dvh] flex flex-col py-3 sm:py-4 md:py-5"
          : "py-6"
      }
    >
      {photos.length > 0 && hints && !isKiosk && (
        <p className="text-gray-500 dark:text-gray-400 text-xs sm:text-sm mb-3">
          {hints}
        </p>
      )}
      <div
        className={`mx-auto w-full max-w-[1500px] flex-shrink-0 ${
          isFullscreen
            ? "mb-1.5 rounded-xl border border-white/55 dark:border-slate-700/70 bg-white/65 dark:bg-slate-900/45 backdrop-blur-md px-2 py-1.5 shadow-lg lg:mb-4 lg:rounded-2xl lg:px-5 lg:py-3"
            : isKiosk
              ? "mb-1.5 px-2 py-1 lg:mb-4 lg:px-5 lg:py-2"
              : "mb-4"
        }`}
      >
        <div
          className={`flex flex-wrap items-center justify-between ${
            isFullscreen || isKiosk ? "gap-2 lg:gap-4" : "gap-3 md:gap-4"
          }`}
        >
          <div className="min-w-0">
            <h1
              className={`font-semibold text-gray-800 dark:text-white truncate ${
                isFullscreen || isKiosk
                  ? "text-sm sm:text-base lg:text-xl xl:text-2xl"
                  : "text-lg sm:text-xl md:text-2xl"
              }`}
            >
              {pageTitle}
            </h1>
            <p
              className={`text-gray-600 dark:text-gray-300 ${
                isFullscreen || isKiosk
                  ? "mt-0 text-[10px] sm:text-xs lg:text-sm"
                  : "mt-0.5 text-[11px] sm:text-xs md:text-sm"
              }`}
            >
              {pageSubtitle}
            </p>
          </div>
          <div
            className={`flex flex-wrap items-center ${
              isFullscreen || isKiosk
                ? "gap-1.5 sm:gap-2 lg:gap-4"
                : "gap-2 sm:gap-3 md:gap-4"
            }`}
          >
            <motion.button
              onClick={handleFullscreenToggle}
              disabled={isFullscreenBusy}
              className={`flex items-center gap-1.5 rounded-lg font-semibold text-white transition-colors ${
                isFullscreen || isKiosk
                  ? "px-2 py-1 text-xs lg:gap-2 lg:px-4 lg:py-2 lg:text-sm"
                  : "gap-2 px-3.5 py-1.5 text-xs md:px-4 md:py-2 md:text-sm"
              } ${
                isFullscreenBusy
                  ? "bg-primary-400 cursor-not-allowed"
                  : "bg-primary-600 hover:bg-primary-700"
              }`}
              aria-label={
                isFullscreen
                  ? "Выйти из полноэкранного режима"
                  : "Полноэкранный режим"
              }
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              {isFullscreen && !isFullscreenBusy ? (
                <FaCompress
                  className={`${isFullscreen || isKiosk ? "w-3.5 h-3.5 lg:w-4 lg:h-4" : "w-4 h-4"}`}
                />
              ) : (
                <FaExpand
                  className={`${isFullscreen || isKiosk ? "w-3.5 h-3.5 lg:w-4 lg:h-4" : "w-4 h-4"}`}
                />
              )}
              <span>
                {isFullscreenBusy
                  ? isFullscreen
                    ? "Выход..."
                    : "Открытие..."
                  : isFullscreen
                    ? "Выход"
                    : "Полный экран"}
              </span>
            </motion.button>
            <span
              className={`inline-flex items-center gap-1.5 rounded-lg border border-white/50 dark:border-slate-700/80 bg-white/55 dark:bg-slate-900/55 text-gray-600 dark:text-gray-300 whitespace-nowrap ${
                isFullscreen || isKiosk
                  ? "px-2 py-1 text-[10px] sm:text-xs lg:gap-2 lg:px-4 lg:py-2 lg:text-base"
                  : "gap-2 px-2.5 py-1.5 text-xs sm:px-3 sm:text-sm md:px-4 md:py-2 md:text-base"
              }`}
            >
              <FaRegCalendarAlt
                className={`opacity-80 ${isFullscreen || isKiosk ? "w-3 h-3 lg:w-4 lg:h-4" : "w-3.5 h-3.5 md:w-4 md:h-4"}`}
              />
              <span className="capitalize">{todayLabel}</span>
            </span>
          </div>
        </div>
      </div>

      <div
        ref={containerRef}
        className={`[scrollbar-width:none] [-ms-overflow-style:none] ${
          isKiosk
            ? "photo-kiosk-marquee-mask flex-1 min-h-0 flex flex-col overflow-x-hidden overflow-y-hidden px-4 sm:px-6 md:px-8 lg:px-10 py-2 sm:py-3 md:py-4 pb-4 sm:pb-5 md:pb-6"
            : "overflow-x-hidden overflow-y-visible py-4 pb-8 px-4 md:px-6"
        }`}
        style={
          isKiosk
            ? {
                paddingBottom: "max(1rem, env(safe-area-inset-bottom, 0px))",
              }
            : undefined
        }
      >
        <div
          className={`flex flex-col flex-1 min-h-0 ${isKiosk ? "gap-2 sm:gap-3 md:gap-4 lg:gap-5 py-1 justify-center" : "gap-4 md:gap-5 py-3 md:py-4"}`}
        >
          {photoRows.map((rowPhotos, rowIndex) => (
            <div
              key={rowIndex}
              className={
                isKiosk
                  ? "overflow-x-hidden overflow-y-visible py-2 sm:py-3 md:py-4 lg:py-5"
                  : "overflow-x-hidden overflow-y-visible py-4 md:py-5"
              }
              style={{ minHeight: 1 }}
            >
              <MarqueeTrack
                items={rowPhotos}
                rowIndex={rowIndex}
                speedPxSec={marqueeSpeed}
                isPaused={!!selectedPhoto || !!hoveredCardKey}
                hoverSpeed={MARQUEE_HOVER_SPEED}
                cardWidthPx={cardWidthPx}
                renderItem={(photo, displayIndex, copyIndex) => {
                  if (photo == null) {
                    return (
                      <div
                        className="flex-shrink-0 rounded-2xl bg-transparent"
                        style={{
                          width: cardWidthPx,
                          height: cardWidthPx + 80,
                        }}
                        aria-hidden
                      />
                    );
                  }
                  const keyIndex =
                    rowIndex * 1_000_000 + copyIndex * 10_000 + displayIndex;
                  const cardIndex = displayIndex;
                  const isHovered =
                    hoveredCardKey === `r${rowIndex}-i${cardIndex}`;
                  return renderPhotoCard(
                    photo,
                    keyIndex,
                    rowIndex,
                    cardIndex,
                    isHovered,
                    kioskNarrowViewport ? cardWidthPx : undefined,
                  );
                }}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  const renderSelectedPhoto = () =>
    selectedPhoto && (
      <AnimatePresence>
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 sm:p-5 md:p-6"
          onClick={() => setSelectedPhoto(null)}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <motion.div
            className="relative w-full max-w-md sm:max-w-lg md:max-w-xl lg:max-w-2xl rounded-2xl md:rounded-3xl overflow-hidden bg-white dark:bg-gray-800 shadow-2xl flex flex-col max-h-[90vh] md:max-h-[85vh] [@media(orientation:landscape)]:max-w-4xl [@media(orientation:landscape)]:max-h-[90vh]"
            onClick={(e) => e.stopPropagation()}
            initial={{ scale: 0.92, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.92, opacity: 0, y: 20 }}
            transition={{ type: "spring", damping: 28, stiffness: 300 }}
          >
            <button
              className="absolute top-3 right-3 z-10 w-9 h-9 md:w-10 md:h-10 rounded-full bg-white/90 dark:bg-gray-700/90 hover:bg-gray-100 dark:hover:bg-gray-600 shadow-md text-gray-700 dark:text-gray-200 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-primary-500 touch-manipulation transition-colors"
              onClick={() => setSelectedPhoto(null)}
              aria-label="Закрыть"
            >
              <FaTimes className="w-4 h-4 md:w-5 md:h-5" />
            </button>

            <div className="flex flex-col flex-1 min-h-0 overflow-y-auto overflow-x-hidden overscroll-contain [@media(orientation:landscape)]:flex-row [@media(orientation:landscape)]:overflow-hidden">
              <div className="relative w-full aspect-square flex items-center justify-center overflow-hidden bg-gradient-to-br from-gray-100 via-white to-gray-200 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 flex-shrink-0 max-h-[50vh] [@media(orientation:landscape)]:max-h-none [@media(orientation:landscape)]:w-[min(42%,85vh)] [@media(orientation:landscape)]:min-w-0 [@media(orientation:landscape)]:aspect-square [@media(orientation:landscape)]:shrink-0">
                <img
                  src={`${apiUrl}${selectedPhoto.photoUrl}`}
                  alt={selectedPhoto.staffFullName}
                  className="w-full h-full object-contain"
                  draggable={false}
                />
              </div>

              <div className="p-5 sm:p-6 md:p-7 flex flex-col gap-3 flex-shrink-0 [@media(orientation:landscape)]:flex-1 [@media(orientation:landscape)]:min-w-0 [@media(orientation:landscape)]:overflow-y-auto [@media(orientation:landscape)]:justify-center">
                <h2 className="text-xl md:text-2xl font-semibold text-gray-800 dark:text-white pr-10 md:pr-12">
                  {selectedPhoto.staffFullName}
                </h2>
                <div className="flex flex-col gap-1.5 text-sm">
                  <p className="text-gray-600 dark:text-gray-300 flex items-center gap-2">
                    <FaBuilding className="w-3.5 h-3.5 shrink-0 opacity-80" />
                    <span>
                      <span className="font-medium text-gray-700 dark:text-gray-200">
                        {getLabelForDepartment(selectedPhoto)}:
                      </span>{" "}
                      {selectedPhoto.department}
                    </span>
                  </p>
                  <p className="text-gray-600 dark:text-gray-300 flex items-center gap-2">
                    <FaClock className="w-3.5 h-3.5 shrink-0 opacity-80" />
                    <span>
                      <span className="font-medium text-gray-700 dark:text-gray-200">
                        Время:
                      </span>{" "}
                      {formatTime(selectedPhoto.attendanceTime)}
                    </span>
                  </p>
                  {selectedPhoto.tutorInfo && (
                    <p className="text-gray-500 dark:text-gray-400 text-xs mt-1 leading-relaxed">
                      {selectedPhoto.tutorInfo}
                    </p>
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        </motion.div>
      </AnimatePresence>
    );

  return (
    <div>
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
