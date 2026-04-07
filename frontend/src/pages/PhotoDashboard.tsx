import React, {
  useState,
  useEffect,
  useLayoutEffect,
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
  FaShieldAlt,
  FaInfoCircle,
  FaCheckCircle,
} from "react-icons/fa";
import {
  PhotoData,
  PhotoManualVerdict,
  PhotoSpoofStatus,
  PhotoWsMessage,
} from "../schemas/IData";
import { apiUrl } from "../../apiConfig";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import apiClient, { log } from "../api";
import useWebSocket from "../hooks/useWebSocket";
import LoaderComponent from "../components/LoaderComponent";
import { Toggle } from "../components/Toggle";
import useWindowSize from "../hooks/useWindowSize";
import EditableDateField from "../components/EditableDateField";

const PING_INTERVAL = 15000;
const PONG_TIMEOUT = 8000;
const MARQUEE_SPEED = 95;
const MARQUEE_HOVER_SPEED = 0;
const SMOOTH_TAU = 0.08;
const MIN_TRACK_COPIES = 2;
const TRACK_COPY_HEADROOM = 2;
const STATIC_TRACK_FIT_THRESHOLD = 1.05;
const HOVER_IDLE_RESUME_MS = 2500;
const STORAGE_KEY_SHOW_ALL_PHOTOS = "photoDashboard_showAllPhotos";
const STORAGE_KEY_SHOW_RISK_ONLY = "photoDashboard_showRiskOnly";
const STORAGE_KEY_VIEW_MODE = "photoDashboard_viewMode";
const STORAGE_KEY_LAST_NON_RISK_MODE = "photoDashboard_lastNonRiskMode";
const WS_MERGE_BUFFER_MS = 180;
const WS_BATCH_FAILSAFE_MS = 300;
const CREATED_NO_PHOTO_MIN_VISIBLE_MS = 2500;
const MARQUEE_VIRTUALIZE_MIN_ITEMS = 56;
const MARQUEE_VIRTUAL_OVERSCAN_ITEMS = 8;
const FILTER_SWITCH_FEEDBACK_MS = 420;
const VERDICT_AUTO_CLOSE_DELAY_MS = 1000;
const VERDICT_AUTO_CLOSE_DELAY_REDUCED_MS = 200;
const VERDICT_SKIP_MODAL_CLOSE_MS = 2000;
const VERDICT_SKIP_MODAL_CLOSE_REDUCED_MS = 800;
const PHOTO_CARD_GRID_STAGGER_STEP = 0.03;

type PhotoUiStatus =
  | "clean"
  | "check"
  | "check_error"
  | "suspicious_auto"
  | "suspicious_manual";

type PhotoDashboardBaseMode = "fresh" | "all";
type PhotoDashboardViewMode = PhotoDashboardBaseMode | "risk";
type CanonicalPhotoEvent = Partial<PhotoData> & {
  op: NonNullable<PhotoData["op"]>;
  stateCode: NonNullable<PhotoData["stateCode"]>;
  versionTs?: string;
};
type PhotoAnimationSurface = "grid" | "marquee";
type PhotoPresenceMode = "card" | "wrapper";

const PHOTO_STATUS_STYLE: Record<
  PhotoUiStatus,
  {
    cardClass: string;
    badgeClass: string;
    label: string;
    showBadgeOnCard: boolean;
  }
> = {
  clean: {
    cardClass: "",
    badgeClass: "bg-slate-700/85 text-slate-100 border border-slate-400/50",
    label: "Нормальное",
    showBadgeOnCard: false,
  },
  check: {
    cardClass: "card-state-check",
    badgeClass: "bg-amber-500/90 text-amber-50 border border-amber-300/70",
    label: "Проверить",
    showBadgeOnCard: true,
  },
  check_error: {
    cardClass: "card-state-check-error",
    badgeClass: "bg-orange-600/90 text-orange-50 border border-orange-300/70",
    label: "Ошибка",
    showBadgeOnCard: true,
  },
  suspicious_auto: {
    cardClass: "card-state-suspicious-auto",
    badgeClass: "bg-rose-600/90 text-rose-50 border border-rose-300/60",
    label: "Подозрительное",
    showBadgeOnCard: true,
  },
  suspicious_manual: {
    cardClass: "card-state-suspicious-manual",
    badgeClass:
      "bg-fuchsia-600/90 text-fuchsia-50 border border-fuchsia-300/65",
    label: "Подозрительное",
    showBadgeOnCard: true,
  },
};

const getStoredShowAllPhotos = (): boolean => {
  try {
    const v = localStorage.getItem(STORAGE_KEY_SHOW_ALL_PHOTOS);
    return v === "true";
  } catch {
    return false;
  }
};

const getStoredShowRiskOnly = (): boolean => {
  try {
    const v = localStorage.getItem(STORAGE_KEY_SHOW_RISK_ONLY);
    return v === "true";
  } catch {
    return false;
  }
};

const isPhotoDashboardBaseMode = (
  value: string | null,
): value is PhotoDashboardBaseMode => value === "fresh" || value === "all";

const isPhotoDashboardViewMode = (
  value: string | null,
): value is PhotoDashboardViewMode =>
  value === "fresh" || value === "all" || value === "risk";

const getInitialDashboardModeState = (): {
  viewMode: PhotoDashboardViewMode;
  lastNonRiskViewMode: PhotoDashboardBaseMode;
} => {
  try {
    const storedViewMode = localStorage.getItem(STORAGE_KEY_VIEW_MODE);
    const storedLastNonRiskMode = localStorage.getItem(
      STORAGE_KEY_LAST_NON_RISK_MODE,
    );
    if (
      isPhotoDashboardViewMode(storedViewMode) &&
      isPhotoDashboardBaseMode(storedLastNonRiskMode)
    ) {
      return {
        viewMode: storedViewMode,
        lastNonRiskViewMode: storedLastNonRiskMode,
      };
    }
  } catch {
    // ignore storage errors
  }

  const showAllPhotos = getStoredShowAllPhotos();
  const showRiskOnly = getStoredShowRiskOnly();
  const lastNonRiskViewMode: PhotoDashboardBaseMode = showAllPhotos
    ? "all"
    : "fresh";

  return {
    viewMode: showRiskOnly ? "risk" : lastNonRiskViewMode,
    lastNonRiskViewMode,
  };
};

const getLabelForDepartment = (photo: PhotoData): string =>
  photo.tutorInfo ? "Группа" : "Отдел";

const timezoneIsoNow = (): string => new Date().toISOString();

const assignPhotoFieldIfDefined = <K extends keyof PhotoData>(
  target: Partial<PhotoData>,
  key: K,
  value: PhotoData[K] | undefined,
): void => {
  if (value !== undefined) {
    target[key] = value;
  }
};

const isHydratedWsInsertEvent = (event: CanonicalPhotoEvent): boolean =>
  event.op === "snapshot" ||
  event.op === "created" ||
  event.stateCode === "SNAPSHOT" ||
  event.stateCode === "PHOTO_ATTACHED" ||
  event.stateCode === "CREATED_NO_PHOTO";

const canInsertCanonicalPhoto = (event: CanonicalPhotoEvent): boolean => {
  if (isHydratedWsInsertEvent(event)) return true;
  return (
    typeof event.staffPin === "string" &&
    typeof event.staffFullName === "string" &&
    typeof event.department === "string" &&
    typeof event.photoUrl === "string" &&
    typeof event.attendanceTime === "string" &&
    typeof event.tutorInfo === "string"
  );
};

const resolvePhotoEffectiveStatus = (
  photo: Partial<PhotoData>,
): PhotoSpoofStatus => {
  if (photo.photoManualVerdict === "clean") return "clean";
  if (photo.photoManualVerdict === "suspicious") return "suspicious";
  return photo.photoSpoofStatus ?? "pending";
};

const resolvePhotoUiStatus = (photo: Partial<PhotoData>): PhotoUiStatus => {
  const manualVerdict = photo.photoManualVerdict ?? "none";
  const effectiveStatus = resolvePhotoEffectiveStatus(photo);
  if (manualVerdict === "suspicious") return "suspicious_manual";
  if (effectiveStatus === "suspicious") return "suspicious_auto";
  if (effectiveStatus === "error") return "check_error";
  if (effectiveStatus === "review" || effectiveStatus === "pending") {
    return "check";
  }
  return "clean";
};

const isManualReviewRequiredByBackend = (
  photo: Partial<PhotoData>,
): boolean => {
  if (typeof photo.photoCanSetManualVerdict === "boolean") {
    return photo.photoCanSetManualVerdict;
  }
  const manualVerdict = photo.photoManualVerdict ?? "none";
  if (manualVerdict !== "none") return false;
  const status = photo.photoSpoofStatus ?? "pending";
  return status === "pending" || status === "review" || status === "error";
};

const isRiskPhotoCandidate = (photo: Partial<PhotoData>): boolean => {
  const manualVerdict = photo.photoManualVerdict ?? "none";
  // В режиме риска показываем:
  // 1) все manual suspicious,
  // 2) auto suspicious,
  // 3) фото, требующие ручной проверки (pending/review/error без manual verdict).
  if (manualVerdict === "suspicious") return true;
  if (manualVerdict === "clean") return false;
  const status = photo.photoSpoofStatus ?? "pending";
  return (
    status === "pending" ||
    status === "review" ||
    status === "error" ||
    status === "suspicious"
  );
};

const buildVerdictSkipFallbackPatch = (
  photo: PhotoData,
  reasonFromServer: string,
): PhotoData => {
  const next: PhotoData = {
    ...photo,
    photoCanSetManualVerdict: false,
  };
  if (reasonFromServer === "status_not_reviewable") {
    const st = photo.photoSpoofStatus ?? "pending";
    if (st === "pending" || st === "review" || st === "error") {
      next.photoSpoofStatus = "clean";
    }
  }
  return next;
};

const stableHash = (value: string): number => {
  let hash = 5381;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 33) ^ value.charCodeAt(i);
  }
  return Math.abs(hash >>> 0);
};

const marqueeItemsStructureSignature = (
  items: (PhotoData | null)[],
): string => {
  const n = items.length;
  if (n === 0) return "0";
  let h = 2166136261;
  for (let i = 0; i < n; i += 1) {
    const p = items[i];
    const id = p?.id ?? -1 - i;
    h ^= id + i * 374761393;
    h = Math.imul(h, 16777619);
  }
  return `${n}:${(h >>> 0).toString(16)}`;
};

const getPhotoIdentity = (
  photo: Partial<PhotoData>,
  fallbackIndex?: number,
): string => {
  if (photo.id != null) {
    return `id:${photo.id}`;
  }
  return [
    `pin:${photo.staffPin ?? ""}`,
    `time:${photo.attendanceTime ?? ""}`,
    `url:${photo.photoUrl ?? ""}`,
    `dept:${photo.department ?? ""}`,
    fallbackIndex != null ? `i:${fallbackIndex}` : "",
  ]
    .filter(Boolean)
    .join("|");
};

const formatTime = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

const comparePhotoSortOrder = (left: PhotoData, right: PhotoData): number => {
  const leftTimestamp = Date.parse(left.attendanceTime ?? "");
  const rightTimestamp = Date.parse(right.attendanceTime ?? "");
  const normalizedLeftTimestamp = Number.isFinite(leftTimestamp)
    ? leftTimestamp
    : 0;
  const normalizedRightTimestamp = Number.isFinite(rightTimestamp)
    ? rightTimestamp
    : 0;
  if (normalizedRightTimestamp !== normalizedLeftTimestamp) {
    return normalizedRightTimestamp - normalizedLeftTimestamp;
  }

  const leftId = left.id ?? -1;
  const rightId = right.id ?? -1;
  if (rightId !== leftId) {
    return rightId - leftId;
  }

  return getPhotoIdentity(left).localeCompare(getPhotoIdentity(right));
};

const sortPhotosDeterministically = (items: PhotoData[]): PhotoData[] => {
  return [...items].sort(comparePhotoSortOrder);
};

const CARD_WIDTH_BASE = 220;
const CARD_WIDTH_SM = 260;
const CARD_WIDTH_MD = 280;
const CARD_WIDTH_LG = 300;
const CARD_WIDTH_XL = 336;
const CARD_WIDTH_2XL = 372;
const CARD_META_HEIGHT = 100;
const ROW_GAP_PX = 12;
const CARD_ITEM_GAP_PX = 16;
const HEADER_ESTIMATE_PX = 200;
const BOTTOM_RESERVE_KIOSK_PX = 40;
const KIOSK_HEADER_RESERVE_PX = 132;
const KIOSK_MAIN_TOP_RESERVE_PX = 24;
const CARD_WIDTH_MIN_PX = 140;
const KIOSK_SHRINK_VIEWPORT_WIDTH = 1280;
const TAPE_NUM_ROWS_MIN = 1;
const TAPE_NUM_ROWS_MAX = 6;
const HANDHELD_LANDSCAPE_MAX_HEIGHT = 1024;
const HANDHELD_LANDSCAPE_MAX_WIDTH = 1400;

const isSingleRowLandscapeViewport = (
  viewportWidth: number,
  viewportHeight: number,
): boolean => {
  return (
    viewportWidth > viewportHeight &&
    viewportHeight <= HANDHELD_LANDSCAPE_MAX_HEIGHT &&
    viewportWidth <= HANDHELD_LANDSCAPE_MAX_WIDTH
  );
};

const getMaxPhotosForViewport = (
  width: number,
  aspectBucket:
    | "portrait-tall"
    | "portrait-classic"
    | "square-ish"
    | "landscape-classic"
    | "landscape-wide"
    | "landscape-ultrawide",
  resolutionTier: "sd" | "hd" | "fhd" | "qhd" | "uhd",
  isKiosk: boolean,
): number => {
  const byTier: Record<typeof resolutionTier, number> = {
    sd: 12,
    hd: 24,
    fhd: 40,
    qhd: 60,
    uhd: 84,
  };
  const byAspect: Record<typeof aspectBucket, number> = {
    "portrait-tall": -8,
    "portrait-classic": -4,
    "square-ish": 0,
    "landscape-classic": 2,
    "landscape-wide": 8,
    "landscape-ultrawide": 12,
  };
  let max = byTier[resolutionTier] + byAspect[aspectBucket];
  if (width < 768) max = Math.min(max, 18);
  if (width < 480) max = Math.min(max, 12);
  if (isKiosk) {
    return Math.min(Math.round(max * 1.4), 140);
  }
  return Math.max(8, max);
};

const getCardWidthForViewport = (viewportWidth: number): number => {
  if (viewportWidth >= 2560) return CARD_WIDTH_2XL;
  if (viewportWidth >= 1920) return CARD_WIDTH_XL;
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

const getPreferredRowsForViewport = (
  viewportWidth: number,
  viewportHeight: number,
): number => {
  const isLandscape = viewportWidth > viewportHeight;
  if (isSingleRowLandscapeViewport(viewportWidth, viewportHeight)) return 1;
  if (isLandscape && viewportWidth >= 1680) return 2;
  if (isLandscape && viewportWidth >= 1024) return 2;
  if (isLandscape && viewportWidth >= 768) return 2;
  if (viewportHeight >= 1200) return 2;
  if (viewportHeight >= 920) return 2;
  return 1;
};

const MarqueeTrack: React.FC<{
  items: (PhotoData | null)[];
  rowIndex: number;
  speedPxSec: number;
  hoverSpeed?: number;
  isPaused: boolean;
  cardWidthPx: number;
  forceLoop?: boolean;
  renderItem: (
    photo: PhotoData | null,
    displayIndex: number,
    copyIndex: number,
    itemIndex: number,
  ) => React.ReactNode;
}> = ({
  items,
  rowIndex,
  speedPxSec,
  hoverSpeed = MARQUEE_HOVER_SPEED,
  isPaused,
  cardWidthPx,
  forceLoop = false,
  renderItem,
}) => {
  type VisibleSlice = {
    start: number;
    end: number;
    seamHeadEnd?: number;
  };
  type VirtualWindowState = {
    copyStart: number;
    copyEnd: number;
    slicesByCopy: Record<number, VisibleSlice>;
    signature: string;
  };
  const containerRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const seqRef = useRef<HTMLUListElement>(null);

  const [seqWidth, setSeqWidth] = useState(0);
  const seqWidthReady = seqWidth > 0;
  const [copyCount, setCopyCount] = useState(MIN_TRACK_COPIES);
  const [shouldAnimate, setShouldAnimate] = useState(true);
  const [virtualWindow, setVirtualWindow] = useState<VirtualWindowState>({
    copyStart: 0,
    copyEnd: MIN_TRACK_COPIES - 1,
    slicesByCopy: {},
    signature: "",
  });

  const offsetRef = useRef(0);
  const velocityRef = useRef(0);
  const lastTimestampRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);
  const seqWidthRef = useRef(0);
  const virtualSignatureRef = useRef("");
  const updateDimensionsFnRef = useRef<() => void>(() => {});
  const cardWidthPxRef = useRef(cardWidthPx);
  const syncVisibleWindowRef = useRef<(force?: boolean) => void>(() => {});

  const shouldVirtualize =
    shouldAnimate && items.length >= MARQUEE_VIRTUALIZE_MIN_ITEMS;
  const itemsStructureSignature = useMemo(
    () => marqueeItemsStructureSignature(items),
    [items],
  );

  const computeVisibleWindow = useCallback(
    (currentOffset: number) => {
      const itemCount = items.length;
      const safeSeqWidth =
        Number.isFinite(seqWidthRef.current) && seqWidthRef.current > 0
          ? seqWidthRef.current
          : 0;
      const containerWidth = containerRef.current?.clientWidth ?? 0;

      if (
        itemCount <= 0 ||
        copyCount <= 0 ||
        safeSeqWidth <= 0 ||
        containerWidth <= 0 ||
        !shouldVirtualize
      ) {
        const allCopies: Record<number, VisibleSlice> = {};
        for (
          let copyIndex = 0;
          copyIndex < Math.max(1, copyCount);
          copyIndex += 1
        ) {
          allCopies[copyIndex] = { start: 0, end: Math.max(0, itemCount - 1) };
        }
        const allEnd = Math.max(0, copyCount - 1);
        return {
          copyStart: 0,
          copyEnd: allEnd,
          slicesByCopy: allCopies,
          signature: `all:${itemCount}:${allEnd}`,
        };
      }

      const itemPitch = safeSeqWidth / itemCount;
      if (!Number.isFinite(itemPitch) || itemPitch <= 0) {
        const allCopies: Record<number, VisibleSlice> = {};
        for (
          let copyIndex = 0;
          copyIndex < Math.max(1, copyCount);
          copyIndex += 1
        ) {
          allCopies[copyIndex] = { start: 0, end: Math.max(0, itemCount - 1) };
        }
        const allEnd = Math.max(0, copyCount - 1);
        return {
          copyStart: 0,
          copyEnd: allEnd,
          slicesByCopy: allCopies,
          signature: `all-pitch:${itemCount}:${allEnd}`,
        };
      }

      const overscanPx = itemPitch * MARQUEE_VIRTUAL_OVERSCAN_ITEMS;
      const leftBound = currentOffset - overscanPx;
      const rightBound = currentOffset + containerWidth + overscanPx;

      const copyStart = Math.max(0, Math.floor(leftBound / safeSeqWidth));
      const copyEnd = Math.min(
        Math.max(0, copyCount - 1),
        Math.ceil(rightBound / safeSeqWidth),
      );

      const slicesByCopy: Record<number, VisibleSlice> = {};
      const signatureParts: string[] = [`${copyStart}:${copyEnd}`];
      let copy0SigIdx = -1;

      for (let copyIndex = copyStart; copyIndex <= copyEnd; copyIndex += 1) {
        const localLeft = leftBound - copyIndex * safeSeqWidth;
        const localRight = rightBound - copyIndex * safeSeqWidth;
        let start = Math.floor(localLeft / itemPitch) - 1;
        let end = Math.ceil(localRight / itemPitch) + 1;
        start = Math.max(0, Math.min(itemCount - 1, start));
        end = Math.max(0, Math.min(itemCount - 1, end));
        if (end < start) continue;
        slicesByCopy[copyIndex] = { start, end };
        if (copyIndex === 0) copy0SigIdx = signatureParts.length;
        signatureParts.push(`${copyIndex}.${start}.${end}`);
      }

      const copy0Slice = slicesByCopy[0];
      if (copy0Slice != null && copy0Slice.start > 0 && copy0SigIdx >= 0) {
        const headEnd = Math.ceil((containerWidth + overscanPx) / itemPitch);
        const seamHeadEnd = Math.min(headEnd, copy0Slice.start - 1);
        slicesByCopy[0] = { ...copy0Slice, seamHeadEnd };
        signatureParts[copy0SigIdx] += `.h${seamHeadEnd}`;
      }

      return {
        copyStart,
        copyEnd,
        slicesByCopy,
        signature: signatureParts.join("|"),
      };
    },
    [copyCount, items.length, shouldVirtualize],
  );

  const syncVisibleWindow = useCallback(
    (force = false) => {
      const safeSeqWidth =
        Number.isFinite(seqWidthRef.current) && seqWidthRef.current > 0
          ? seqWidthRef.current
          : 1;
      const normalizedOffset =
        ((offsetRef.current % safeSeqWidth) + safeSeqWidth) % safeSeqWidth;
      const nextWindow = computeVisibleWindow(normalizedOffset);
      if (!force && virtualSignatureRef.current === nextWindow.signature) {
        return;
      }
      virtualSignatureRef.current = nextWindow.signature;
      setVirtualWindow((prev) =>
        prev.signature === nextWindow.signature ? prev : nextWindow,
      );
    },
    [computeVisibleWindow],
  );

  const updateDimensions = useCallback(() => {
    if (items.length === 0) return;
    const containerWidth = containerRef.current?.clientWidth ?? 0;

    const sequenceWidth = items.length * (cardWidthPx + CARD_ITEM_GAP_PX);
    const roundedSequenceWidth = Math.ceil(sequenceWidth);

    const previousWidth = seqWidthRef.current;
    if (
      cardWidthPxRef.current !== cardWidthPx &&
      previousWidth > 0 &&
      roundedSequenceWidth > 0
    ) {
      const normalizedProgress =
        (((offsetRef.current % previousWidth) + previousWidth) %
          previousWidth) /
        previousWidth;
      offsetRef.current = normalizedProgress * roundedSequenceWidth;
    }
    cardWidthPxRef.current = cardWidthPx;
    seqWidthRef.current = roundedSequenceWidth;
    setSeqWidth((prev) =>
      prev === roundedSequenceWidth ? prev : roundedSequenceWidth,
    );

    const canAnimate = forceLoop
      ? items.length > 0
      : roundedSequenceWidth > containerWidth * STATIC_TRACK_FIT_THRESHOLD;
    setShouldAnimate((prev) => (prev === canAnimate ? prev : canAnimate));
    if (!canAnimate) {
      setCopyCount((prev) => (prev === 1 ? prev : 1));
      return;
    }

    const copiesNeeded =
      Math.ceil(containerWidth / roundedSequenceWidth) + TRACK_COPY_HEADROOM;
    const nextCopyCount = Math.max(MIN_TRACK_COPIES, copiesNeeded);
    setCopyCount((prev) => (prev === nextCopyCount ? prev : nextCopyCount));
    syncVisibleWindow(true);
  }, [syncVisibleWindow, forceLoop, items.length, cardWidthPx]);

  const dimensionRafRef = useRef<number | null>(null);
  const scheduleDimensionsUpdate = useCallback(() => {
    if (dimensionRafRef.current !== null) return;
    dimensionRafRef.current = requestAnimationFrame(() => {
      dimensionRafRef.current = null;
      updateDimensions();
    });
  }, [updateDimensions]);

  useLayoutEffect(() => {
    updateDimensionsFnRef.current = updateDimensions;
  }, [updateDimensions]);

  useLayoutEffect(() => {
    virtualSignatureRef.current = "";
    offsetRef.current = 0;
    velocityRef.current = 0;
    lastTimestampRef.current = null;
    if (trackRef.current) {
      trackRef.current.style.transform = "translate3d(0, 0, 0)";
    }
    updateDimensionsFnRef.current();
  }, [rowIndex]);

  useLayoutEffect(() => {
    updateDimensionsFnRef.current();
  }, [itemsStructureSignature]);

  useLayoutEffect(() => {
    syncVisibleWindowRef.current = syncVisibleWindow;
  }, [syncVisibleWindow]);

  useEffect(() => {
    syncVisibleWindow(true);
  }, [syncVisibleWindow, copyCount, shouldVirtualize, items.length]);

  useEffect(() => {
    if (!window.ResizeObserver) {
      window.addEventListener("resize", scheduleDimensionsUpdate);
      return () => {
        window.removeEventListener("resize", scheduleDimensionsUpdate);
        if (dimensionRafRef.current !== null) {
          cancelAnimationFrame(dimensionRafRef.current);
          dimensionRafRef.current = null;
        }
      };
    }

    const ro = new ResizeObserver(() => scheduleDimensionsUpdate());
    if (containerRef.current) ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      if (dimensionRafRef.current !== null) {
        cancelAnimationFrame(dimensionRafRef.current);
        dimensionRafRef.current = null;
      }
    };
  }, [scheduleDimensionsUpdate]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.hidden) {
        lastTimestampRef.current = null;
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  useLayoutEffect(() => {
    const track = trackRef.current;
    if (!track || seqWidthRef.current <= 0) return;

    if (!shouldAnimate) {
      track.style.transform = "translate3d(0, 0, 0)";
      syncVisibleWindowRef.current(true);
      return;
    }

    if (isPaused && hoverSpeed === 0) {
      velocityRef.current = 0;
      lastTimestampRef.current = null;
      track.style.transform = `translate3d(-${offsetRef.current}px, 0, 0)`;
      syncVisibleWindowRef.current(true);
      return;
    }

    const currentSeqWidth = seqWidthRef.current;
    const safeSeqWidth =
      Number.isFinite(currentSeqWidth) && currentSeqWidth > 0
        ? currentSeqWidth
        : 1;
    offsetRef.current =
      ((offsetRef.current % safeSeqWidth) + safeSeqWidth) % safeSeqWidth;
    track.style.transform = `translate3d(-${offsetRef.current}px, 0, 0)`;

    const animate = (timestamp: number) => {
      if (lastTimestampRef.current === null) {
        lastTimestampRef.current = timestamp;
      }

      const dt = Math.min(
        0.1,
        Math.max(0, timestamp - lastTimestampRef.current) / 1000,
      );
      lastTimestampRef.current = timestamp;

      const targetVelocity = isPaused ? hoverSpeed : speedPxSec;
      const easingFactor = 1 - Math.exp(-dt / SMOOTH_TAU);
      velocityRef.current +=
        (targetVelocity - velocityRef.current) * easingFactor;

      const sw = seqWidthRef.current;
      const safeSw = Number.isFinite(sw) && sw > 0 ? sw : 1;
      const prevOffset = offsetRef.current;
      let nextOffset = prevOffset + velocityRef.current * dt;
      const didWrap =
        Math.floor(nextOffset / safeSw) !== Math.floor(prevOffset / safeSw);
      nextOffset = ((nextOffset % safeSw) + safeSw) % safeSw;
      offsetRef.current = nextOffset;

      track.style.transform = `translate3d(-${nextOffset}px, 0, 0)`;
      syncVisibleWindowRef.current(didWrap);
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
  }, [seqWidthReady, speedPxSec, hoverSpeed, isPaused, shouldAnimate]);

  const safeItemPitch = cardWidthPx + CARD_ITEM_GAP_PX;
  const maxCopyIndex = Math.max(0, copyCount - 1);
  const copyStart = shouldVirtualize
    ? Math.min(virtualWindow.copyStart, maxCopyIndex)
    : 0;
  const copyEnd = shouldVirtualize
    ? Math.max(copyStart, Math.min(virtualWindow.copyEnd, maxCopyIndex))
    : maxCopyIndex;
  const renderedCopyCount = Math.max(1, copyEnd - copyStart + 1);

  return (
    <div
      ref={containerRef}
      className="relative overflow-x-hidden overflow-y-hidden"
    >
      <div
        ref={trackRef}
        className={`flex ${shouldAnimate ? "w-max will-change-transform" : "w-full justify-center"} ${isPaused ? "photo-marquee-paused" : ""}`}
      >
        {Array.from({ length: renderedCopyCount }, (_, localCopyIndex) => {
          const copyIndex = copyStart + localCopyIndex;
          const visibleSlice = virtualWindow.slicesByCopy[copyIndex];
          const hasVisibleSlice =
            shouldVirtualize &&
            visibleSlice != null &&
            visibleSlice.end >= visibleSlice.start;
          const startIndex = hasVisibleSlice ? visibleSlice.start : 0;
          const endIndex = hasVisibleSlice
            ? visibleSlice.end
            : items.length - 1;
          const seamHeadEnd = hasVisibleSlice
            ? visibleSlice.seamHeadEnd
            : undefined;

          const leftSpacerWidth =
            hasVisibleSlice && seamHeadEnd == null
              ? Math.max(0, startIndex * safeItemPitch)
              : 0;
          const gapSpacerWidth =
            seamHeadEnd != null
              ? Math.max(0, (startIndex - seamHeadEnd - 1) * safeItemPitch)
              : 0;
          const rightSpacerWidth = Math.max(
            0,
            (items.length - endIndex - 1) * safeItemPitch,
          );

          const renderItem_ = (
            photo: (typeof items)[number],
            itemIndex: number,
          ) => {
            const displayIndex = copyIndex * items.length + itemIndex;
            const key =
              photo != null
                ? `row-${rowIndex}-${copyIndex}-${photo.id ?? `${photo.staffPin}-${photo.attendanceTime}`}`
                : `row-${rowIndex}-${copyIndex}-empty-${itemIndex}`;
            const style = photo == null ? { width: cardWidthPx } : undefined;
            return (
              <li
                key={key}
                className="mr-4 my-1 flex-shrink-0 list-none"
                style={style}
              >
                {renderItem(photo, displayIndex, copyIndex, itemIndex)}
              </li>
            );
          };

          return (
            <ul
              key={`row-${rowIndex}-copy-${copyIndex}`}
              ref={copyIndex === 0 ? seqRef : undefined}
              className="flex items-center"
              aria-hidden={copyIndex > 0}
            >
              {seamHeadEnd != null &&
                items
                  .slice(0, seamHeadEnd + 1)
                  .map((photo, i) => renderItem_(photo, i))}

              {seamHeadEnd != null && gapSpacerWidth > 0 && (
                <li
                  key={`row-${rowIndex}-copy-${copyIndex}-gap-spacer`}
                  className="my-1 flex-shrink-0 list-none"
                  style={{ width: gapSpacerWidth }}
                  aria-hidden
                />
              )}
              {hasVisibleSlice &&
                seamHeadEnd == null &&
                leftSpacerWidth > 0 && (
                  <li
                    key={`row-${rowIndex}-copy-${copyIndex}-left-spacer`}
                    className="my-1 flex-shrink-0 list-none"
                    style={{ width: leftSpacerWidth }}
                    aria-hidden
                  />
                )}

              {items
                .slice(startIndex, endIndex + 1)
                .map((photo, localItemIndex) =>
                  renderItem_(photo, startIndex + localItemIndex),
                )}

              {hasVisibleSlice && rightSpacerWidth > 0 && (
                <li
                  key={`row-${rowIndex}-copy-${copyIndex}-right-spacer`}
                  className="my-1 flex-shrink-0 list-none"
                  style={{ width: rightSpacerWidth }}
                  aria-hidden
                />
              )}
            </ul>
          );
        })}
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

interface WsBatchBucket {
  messageType: "initial_photos" | "photos_updated";
  totalChunks: number;
  receivedChunks: Set<number>;
  events: PhotoData[];
  timeoutId: number;
}

type PhotoVerdictAction = "manual_suspicious" | "manual_clean" | "manual_reset";

const resolvePhotoSrc = (photoUrl: string): string => {
  if (!photoUrl) return "";
  if (/^https?:\/\//i.test(photoUrl)) return photoUrl;
  return `${apiUrl}${photoUrl}`;
};

const PhotoImageFallback: React.FC<{
  reason: "missing" | "error";
  containerClassName: string;
  iconWrapperClassName: string;
  iconClassName: string;
  labelClassName: string;
}> = React.memo(
  ({
    reason,
    containerClassName,
    iconWrapperClassName,
    iconClassName,
    labelClassName,
  }) => (
    <div className={containerClassName}>
      <div className={iconWrapperClassName}>
        <FaImage className={iconClassName} />
      </div>
      <span className={labelClassName}>
        {reason === "error" ? "Фото недоступно" : "Фото не загружено"}
      </span>
    </div>
  ),
);
PhotoImageFallback.displayName = "PhotoImageFallback";

const PhotoImageAsset: React.FC<{
  photo: PhotoData;
  imageClassName: string;
  placeholderContainerClassName: string;
  placeholderIconWrapperClassName: string;
  placeholderIconClassName: string;
  placeholderLabelClassName: string;
  decoding?: "async" | "auto" | "sync";
  loading?: "eager" | "lazy";
}> = React.memo(
  ({
    photo,
    imageClassName,
    placeholderContainerClassName,
    placeholderIconWrapperClassName,
    placeholderIconClassName,
    placeholderLabelClassName,
    decoding,
    loading,
  }) => {
    const src = useMemo(
      () => resolvePhotoSrc(photo.photoUrl),
      [photo.photoUrl],
    );
    const [isImageUnavailable, setIsImageUnavailable] = useState(false);

    useEffect(() => {
      setIsImageUnavailable(false);
    }, [photo.id, src]);

    const fallbackReason: "missing" | "error" =
      photo.hasPhoto === false || !src ? "missing" : "error";

    if (photo.hasPhoto === false || !src || isImageUnavailable) {
      return (
        <PhotoImageFallback
          reason={fallbackReason}
          containerClassName={placeholderContainerClassName}
          iconWrapperClassName={placeholderIconWrapperClassName}
          iconClassName={placeholderIconClassName}
          labelClassName={placeholderLabelClassName}
        />
      );
    }

    return (
      <img
        src={src}
        alt={photo.staffFullName}
        className={imageClassName}
        loading={loading}
        decoding={decoding}
        draggable={false}
        onError={() => setIsImageUnavailable(true)}
      />
    );
  },
);
PhotoImageAsset.displayName = "PhotoImageAsset";

const PhotoCardImage: React.FC<{
  photo: PhotoData;
  isClone: boolean;
}> = React.memo(({ photo, isClone }) => {
  return (
    <PhotoImageAsset
      photo={photo}
      imageClassName="w-full h-full object-contain transition-opacity duration-300"
      loading="lazy"
      decoding={isClone ? "async" : "auto"}
      placeholderContainerClassName="w-full h-full flex flex-col items-center justify-center gap-2 bg-gradient-to-br from-slate-100/95 via-white to-slate-200/95 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900"
      placeholderIconWrapperClassName="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-900/10 text-slate-600 dark:bg-slate-100/10 dark:text-slate-200"
      placeholderIconClassName="h-7 w-7"
      placeholderLabelClassName="rounded-full bg-black/55 px-2.5 py-1 text-[11px] font-medium text-white shadow-md backdrop-blur-sm"
    />
  );
});
PhotoCardImage.displayName = "PhotoCardImage";

const PhotoDashboard: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const prefersReducedMotion = !!useReducedMotion();
  const isKiosk =
    /\/photo$/.test(location.pathname) &&
    new URLSearchParams(location.search).get("kiosk") === "1";

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isFullscreenBusy, setIsFullscreenBusy] = useState(false);
  const [photos, setPhotos] = useState<PhotoData[]>([]);
  const photosRef = useRef<PhotoData[]>([]);
  const [selectedPhoto, setSelectedPhoto] = useState<PhotoData | null>(null);
  const selectedPhotoRef = useRef<PhotoData | null>(null);
  const [isVerdictSubmitting, setIsVerdictSubmitting] = useState(false);
  const [verdictError, setVerdictError] = useState("");
  const [verdictSkipNotice, setVerdictSkipNotice] = useState("");
  const [verdictAutoClosePending, setVerdictAutoClosePending] = useState(false);
  const verdictCloseTimerRef = useRef<number | null>(null);
  const photoTapeRowByIdRef = useRef<Map<number, number>>(new Map());
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

  const clearScheduledVerdictModalClose = useCallback(() => {
    if (verdictCloseTimerRef.current != null) {
      window.clearTimeout(verdictCloseTimerRef.current);
      verdictCloseTimerRef.current = null;
    }
    setVerdictAutoClosePending(false);
    setVerdictSkipNotice("");
  }, []);

  useEffect(() => {
    setVerdictError("");
    clearScheduledVerdictModalClose();
  }, [selectedPhoto?.id, clearScheduledVerdictModalClose]);

  useEffect(() => {
    photosRef.current = photos;
  }, [photos]);

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

  const pageTitle = isFullscreen
    ? "Лента фотографий посещаемости"
    : "Фотографии посещаемости";

  const [loading, setLoading] = useState<boolean>(true);
  const initialLoadDoneRef = useRef<boolean>(false);
  const [viewMode, setViewMode] = useState<PhotoDashboardViewMode>(
    () => getInitialDashboardModeState().viewMode,
  );
  const [lastNonRiskViewMode, setLastNonRiskViewMode] =
    useState<PhotoDashboardBaseMode>(
      () => getInitialDashboardModeState().lastNonRiskViewMode,
    );
  const [isDisplayFilterPending, setIsDisplayFilterPending] =
    useState<boolean>(false);
  const filterSwitchTimerRef = useRef<number | null>(null);
  const [isPageVisible, setIsPageVisible] = useState<boolean>(() =>
    typeof document === "undefined"
      ? true
      : document.visibilityState === "visible",
  );
  const [hoveredPhotoKey, setHoveredPhotoKey] = useState<string | null>(null);
  const showRiskOnly = viewMode === "risk";
  const showAllPhotos =
    (showRiskOnly ? lastNonRiskViewMode : viewMode) === "all";
  const isFreshMode = viewMode === "fresh";
  const useStaticPhotoGridMode = isFullscreen;

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY_VIEW_MODE, viewMode);
      localStorage.setItem(STORAGE_KEY_LAST_NON_RISK_MODE, lastNonRiskViewMode);
      localStorage.removeItem(STORAGE_KEY_SHOW_ALL_PHOTOS);
      localStorage.removeItem(STORAGE_KEY_SHOW_RISK_ONLY);
    } catch {
      // ignore storage errors
    }
  }, [lastNonRiskViewMode, viewMode]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsPageVisible(document.visibilityState === "visible");
    };

    handleVisibilityChange();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () =>
      document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, []);
  const clearPendingFilterWork = useCallback(() => {
    if (filterSwitchTimerRef.current != null) {
      window.clearTimeout(filterSwitchTimerRef.current);
      filterSwitchTimerRef.current = null;
    }
  }, []);

  const schedulePendingFilterReset = useCallback(() => {
    clearPendingFilterWork();
    filterSwitchTimerRef.current = window.setTimeout(() => {
      filterSwitchTimerRef.current = null;
      setIsDisplayFilterPending(false);
    }, FILTER_SWITCH_FEEDBACK_MS);
  }, [clearPendingFilterWork]);

  const queueAppliedFilterUpdate = useCallback(() => {
    setHoveredPhotoKey(null);
    setIsDisplayFilterPending(true);
    schedulePendingFilterReset();
  }, [schedulePendingFilterReset]);

  const handleRiskOnlyToggleChange = useCallback(
    (nextValue: boolean) => {
      const nextViewMode: PhotoDashboardViewMode = nextValue
        ? "risk"
        : lastNonRiskViewMode;
      if (nextViewMode === viewMode) {
        return;
      }
      queueAppliedFilterUpdate();
      setViewMode(nextViewMode);
    },
    [lastNonRiskViewMode, queueAppliedFilterUpdate, viewMode],
  );

  const handleShowAllPhotosToggleChange = useCallback(
    (nextValue: boolean) => {
      const nextBaseMode: PhotoDashboardBaseMode = nextValue ? "all" : "fresh";
      if (showRiskOnly) {
        if (lastNonRiskViewMode === nextBaseMode) {
          return;
        }
        queueAppliedFilterUpdate();
        setLastNonRiskViewMode(nextBaseMode);
        return;
      }
      if (viewMode === nextBaseMode && lastNonRiskViewMode === nextBaseMode) {
        return;
      }
      queueAppliedFilterUpdate();
      setViewMode(nextBaseMode);
      setLastNonRiskViewMode(nextBaseMode);
    },
    [lastNonRiskViewMode, queueAppliedFilterUpdate, showRiskOnly, viewMode],
  );

  useEffect(() => {
    return () => {
      clearPendingFilterWork();
    };
  }, [clearPendingFilterWork]);

  const lastPointerActivityRef = useRef<number>(Date.now());
  const cardRefs = useRef<Map<string, HTMLElement | null>>(new Map());
  const [activeCardCoords, setActiveCardCoords] = useState<{
    row: number;
    col: number;
  } | null>(null);
  const [activePhotoKey, setActivePhotoKey] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [cardWidthPx, setCardWidthPx] = useState<number>(CARD_WIDTH_MD);
  const [tapeNumRows, setTapeNumRows] = useState<number>(3);
  const [kioskNarrowViewport, setKioskNarrowViewport] =
    useState<boolean>(false);
  const viewport = useWindowSize();
  const wsMergeBufferRef = useRef<PhotoData[]>([]);
  const wsMergeTimerRef = useRef<number | null>(null);
  const wsBatchBucketsRef = useRef<Map<string, WsBatchBucket>>(new Map());
  const noPhotoFirstSeenRef = useRef<Map<number, number>>(new Map());
  const delayedPhotoAttachTimersRef = useRef<Map<number, number>>(new Map());
  const lastVersionByIdRef = useRef<Map<number, string>>(new Map());
  const enqueueWsEventsRef = useRef<(events: PhotoData[]) => void>(() => {});

  const getCurrentLocalDate = useCallback((): string => {
    const today = new Date();
    const year = today.getFullYear();
    const month = `0${today.getMonth() + 1}`.slice(-2);
    const day = `0${today.getDate()}`.slice(-2);
    return `${year}-${month}-${day}`;
  }, []);

  const [selectedDate, setSelectedDate] = useState<string>(() => {
    const today = new Date();
    const year = today.getFullYear();
    const month = `0${today.getMonth() + 1}`.slice(-2);
    const day = `0${today.getDate()}`.slice(-2);
    return `${year}-${month}-${day}`;
  });

  const date = selectedDate;
  log.info("Connecting with date:", date);

  const isSelectedDateToday = selectedDate === getCurrentLocalDate();

  const todayLabel = useMemo(() => {
    const parts = selectedDate.split("-").map(Number);
    const d = new Date(parts[0], parts[1] - 1, parts[2]);
    return d.toLocaleDateString("ru-RU", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  }, [selectedDate]);

  const pageSubtitle = isFullscreen
    ? "Режим показа в реальном времени"
    : isSelectedDateToday
      ? "Актуальные отметки за текущий день"
      : "Архивные отметки за выбранный день";

  useEffect(() => {
    initialLoadDoneRef.current = false;
    setLoading(true);
    photoTapeRowByIdRef.current.clear();
  }, [date]);

  const getMaxPhotos = useCallback(() => {
    return getMaxPhotosForViewport(
      viewport.width,
      viewport.aspectBucket,
      viewport.resolutionTier,
      isKiosk,
    );
  }, [isKiosk, viewport.width, viewport.aspectBucket, viewport.resolutionTier]);

  const extractEventsFromMessage = useCallback(
    (data: PhotoWsMessage): PhotoData[] => {
      if (Array.isArray(data.events)) return data.events;
      if (Array.isArray(data.photos)) return data.photos;
      if (data.newPhoto) return [data.newPhoto];
      return [];
    },
    [],
  );

  const normalizeWsEvent = useCallback(
    (eventData: PhotoData): CanonicalPhotoEvent => {
      const normalizedOp =
        eventData.op ??
        (eventData.stateCode === "DELETED"
          ? "deleted"
          : eventData.stateCode === "SNAPSHOT"
            ? "snapshot"
            : "updated");
      const normalizedState =
        eventData.stateCode ??
        (normalizedOp === "snapshot"
          ? "SNAPSHOT"
          : normalizedOp === "deleted"
            ? "DELETED"
            : normalizedOp === "created" && eventData.hasPhoto === false
              ? "CREATED_NO_PHOTO"
              : eventData.hasPhoto
                ? "PHOTO_ATTACHED"
                : "UPDATED_META");
      const normalizedEvent: CanonicalPhotoEvent = {
        op: normalizedOp,
        stateCode: normalizedState,
        versionTs: eventData.versionTs,
      };

      assignPhotoFieldIfDefined(normalizedEvent, "id", eventData.id);
      assignPhotoFieldIfDefined(
        normalizedEvent,
        "hasPhoto",
        eventData.hasPhoto,
      );

      if (isHydratedWsInsertEvent(normalizedEvent)) {
        normalizedEvent.staffPin = eventData.staffPin ?? "";
        normalizedEvent.staffFullName = eventData.staffFullName ?? "";
        normalizedEvent.department = eventData.department ?? "";
        normalizedEvent.photoUrl = eventData.photoUrl ?? "";
        normalizedEvent.attendanceTime =
          eventData.attendanceTime ?? timezoneIsoNow();
        normalizedEvent.tutorInfo = eventData.tutorInfo ?? "";
        normalizedEvent.photoSpoofStatus =
          eventData.photoSpoofStatus ?? "pending";
        normalizedEvent.photoManualVerdict =
          eventData.photoManualVerdict ?? "none";
      } else {
        assignPhotoFieldIfDefined(
          normalizedEvent,
          "staffPin",
          eventData.staffPin,
        );
        assignPhotoFieldIfDefined(
          normalizedEvent,
          "staffFullName",
          eventData.staffFullName,
        );
        assignPhotoFieldIfDefined(
          normalizedEvent,
          "department",
          eventData.department,
        );
        assignPhotoFieldIfDefined(
          normalizedEvent,
          "photoUrl",
          eventData.photoUrl,
        );
        assignPhotoFieldIfDefined(
          normalizedEvent,
          "attendanceTime",
          eventData.attendanceTime,
        );
        assignPhotoFieldIfDefined(
          normalizedEvent,
          "tutorInfo",
          eventData.tutorInfo,
        );
        assignPhotoFieldIfDefined(
          normalizedEvent,
          "photoSpoofStatus",
          eventData.photoSpoofStatus,
        );
        assignPhotoFieldIfDefined(
          normalizedEvent,
          "photoManualVerdict",
          eventData.photoManualVerdict,
        );
      }

      if (typeof eventData.photoCanSetManualVerdict === "boolean") {
        normalizedEvent.photoCanSetManualVerdict =
          eventData.photoCanSetManualVerdict;
      }

      return normalizedEvent;
    },
    [],
  );

  const materializeCanonicalPhoto = useCallback(
    (eventData: Partial<PhotoData>, existingPhoto?: PhotoData): PhotoData => {
      const merged = existingPhoto
        ? { ...existingPhoto, ...eventData }
        : { ...eventData };
      const normalizedManualVerdict = merged.photoManualVerdict ?? "none";
      const normalizedSpoofStatus = merged.photoSpoofStatus ?? "pending";

      return {
        id: merged.id,
        hasPhoto: merged.hasPhoto,
        staffPin: merged.staffPin ?? "",
        staffFullName: merged.staffFullName ?? "",
        department: merged.department ?? "",
        photoUrl: merged.photoUrl ?? "",
        attendanceTime: merged.attendanceTime ?? timezoneIsoNow(),
        tutorInfo: merged.tutorInfo ?? "",
        photoSpoofStatus: normalizedSpoofStatus,
        photoManualVerdict: normalizedManualVerdict,
        photoCanSetManualVerdict:
          typeof merged.photoCanSetManualVerdict === "boolean"
            ? merged.photoCanSetManualVerdict
            : isManualReviewRequiredByBackend({
                photoManualVerdict: normalizedManualVerdict,
                photoSpoofStatus: normalizedSpoofStatus,
              }),
        op: merged.op,
        stateCode: merged.stateCode,
        versionTs: merged.versionTs,
      };
    },
    [],
  );

  const clearDelayedPhotoAttachTimers = useCallback(() => {
    delayedPhotoAttachTimersRef.current.forEach((timerId) =>
      window.clearTimeout(timerId),
    );
    delayedPhotoAttachTimersRef.current.clear();
  }, []);

  const syncSelectedPhotoWithList = useCallback((nextPhotos: PhotoData[]) => {
    setSelectedPhoto((prev) => {
      if (!prev) return prev;
      const prevKey = getPhotoIdentity(prev);
      const matched = nextPhotos.find(
        (photo) => getPhotoIdentity(photo) === prevKey,
      );
      return matched ?? null;
    });
  }, []);

  const commitCanonicalPhotos = useCallback(
    (
      nextPhotos: PhotoData[],
      options: {
        finishLoading?: boolean;
      } = {},
    ) => {
      const sorted = sortPhotosDeterministically(nextPhotos);
      photosRef.current = sorted;
      syncSelectedPhotoWithList(sorted);
      setPhotos(sorted);
      if (options.finishLoading) {
        setLoading(false);
      }
    },
    [syncSelectedPhotoWithList],
  );

  const mergeCanonicalPhotoEvents = useCallback(
    (
      events: PhotoData[],
      options: {
        replace?: boolean;
        finishLoading?: boolean;
      } = {},
    ) => {
      const normalizedEvents = events.map(normalizeWsEvent);
      const isReplace = options.replace === true;

      if (isReplace) {
        noPhotoFirstSeenRef.current.clear();
        clearDelayedPhotoAttachTimers();
        lastVersionByIdRef.current.clear();
        photoTapeRowByIdRef.current.clear();
      }

      const next = isReplace ? [] : [...photosRef.current];
      for (const eventData of normalizedEvents) {
        const eventId = eventData.id;
        if (eventId != null && eventData.versionTs) {
          const lastVersion = lastVersionByIdRef.current.get(eventId);
          const incomingMs = Date.parse(eventData.versionTs);
          const lastMs = lastVersion ? Date.parse(lastVersion) : NaN;
          const bothFinite =
            Number.isFinite(incomingMs) && Number.isFinite(lastMs);
          if (!isReplace && bothFinite && incomingMs < lastMs) {
            continue;
          }
          lastVersionByIdRef.current.set(eventId, eventData.versionTs);
        }

        if (eventData.stateCode === "DELETED" || eventData.op === "deleted") {
          if (eventId != null) {
            const existingIdx = next.findIndex((item) => item.id === eventId);
            if (existingIdx >= 0) {
              next.splice(existingIdx, 1);
            }
            const pendingTimer =
              delayedPhotoAttachTimersRef.current.get(eventId);
            if (pendingTimer != null) {
              window.clearTimeout(pendingTimer);
              delayedPhotoAttachTimersRef.current.delete(eventId);
            }
            noPhotoFirstSeenRef.current.delete(eventId);
            lastVersionByIdRef.current.delete(eventId);
          }
          continue;
        }

        if (eventId != null && eventData.stateCode === "CREATED_NO_PHOTO") {
          if (!noPhotoFirstSeenRef.current.has(eventId)) {
            noPhotoFirstSeenRef.current.set(eventId, Date.now());
          }
        }

        if (eventId != null && eventData.stateCode === "PHOTO_ATTACHED") {
          const seenAt = noPhotoFirstSeenRef.current.get(eventId);
          if (seenAt != null) {
            const elapsed = Date.now() - seenAt;
            if (elapsed < CREATED_NO_PHOTO_MIN_VISIBLE_MS) {
              const pendingTimer =
                delayedPhotoAttachTimersRef.current.get(eventId);
              if (pendingTimer != null) {
                window.clearTimeout(pendingTimer);
              }
              const waitMs = CREATED_NO_PHOTO_MIN_VISIBLE_MS - elapsed;
              const timerId = window.setTimeout(() => {
                delayedPhotoAttachTimersRef.current.delete(eventId);
                enqueueWsEventsRef.current([
                  materializeCanonicalPhoto(eventData),
                ]);
              }, waitMs);
              delayedPhotoAttachTimersRef.current.set(eventId, timerId);
              continue;
            }
            noPhotoFirstSeenRef.current.delete(eventId);
          }
        }

        const eventKey = getPhotoIdentity(eventData);
        const existingIdx =
          eventId != null
            ? next.findIndex((item) => item.id === eventId)
            : next.findIndex((item) => getPhotoIdentity(item) === eventKey);

        if (existingIdx >= 0) {
          next[existingIdx] = materializeCanonicalPhoto(
            eventData,
            next[existingIdx],
          );
        } else if (canInsertCanonicalPhoto(eventData)) {
          next.push(materializeCanonicalPhoto(eventData));
        }
      }

      commitCanonicalPhotos(next, { finishLoading: options.finishLoading });
    },
    [
      clearDelayedPhotoAttachTimers,
      commitCanonicalPhotos,
      materializeCanonicalPhoto,
      normalizeWsEvent,
    ],
  );

  const applyInitialSnapshot = useCallback(
    (events: PhotoData[]) => {
      wsMergeBufferRef.current = [];
      if (wsMergeTimerRef.current != null) {
        window.clearTimeout(wsMergeTimerRef.current);
        wsMergeTimerRef.current = null;
      }
      wsBatchBucketsRef.current.forEach((bucket) => {
        window.clearTimeout(bucket.timeoutId);
      });
      wsBatchBucketsRef.current.clear();
      const apply = () => {
        mergeCanonicalPhotoEvents(events, {
          replace: true,
          finishLoading: true,
        });
        initialLoadDoneRef.current = true;
      };
      if (events.length > 400) {
        queueMicrotask(apply);
      } else {
        apply();
      }
    },
    [mergeCanonicalPhotoEvents],
  );

  const flushWsMergeBuffer = useCallback(() => {
    if (wsMergeTimerRef.current != null) {
      window.clearTimeout(wsMergeTimerRef.current);
    }
    wsMergeTimerRef.current = null;
    const buffered = wsMergeBufferRef.current;
    if (buffered.length === 0) return;
    wsMergeBufferRef.current = [];

    const dedupById = new Map<number, PhotoData>();
    const withoutId: PhotoData[] = [];
    buffered.forEach((evt) => {
      if (evt.id == null) {
        withoutId.push(evt);
        return;
      }
      dedupById.set(evt.id, evt);
    });
    const batch = [...withoutId, ...Array.from(dedupById.values())];
    if (batch.length > 400) {
      queueMicrotask(() => {
        mergeCanonicalPhotoEvents(batch);
      });
    } else {
      mergeCanonicalPhotoEvents(batch);
    }
  }, [mergeCanonicalPhotoEvents]);

  const enqueueWsEvents = useCallback(
    (events: PhotoData[]) => {
      if (!events.length) return;
      wsMergeBufferRef.current.push(...events);
      if (wsMergeTimerRef.current != null) return;
      wsMergeTimerRef.current = window.setTimeout(
        flushWsMergeBuffer,
        WS_MERGE_BUFFER_MS,
      );
    },
    [flushWsMergeBuffer],
  );

  useEffect(() => {
    enqueueWsEventsRef.current = enqueueWsEvents;
  }, [enqueueWsEvents]);

  const collectChunkedEvents = useCallback(
    (
      messageType: "initial_photos" | "photos_updated",
      data: PhotoWsMessage,
      events: PhotoData[],
    ): PhotoData[] | null => {
      const totalChunks = Math.max(1, Number(data.totalChunks) || 1);
      if (totalChunks <= 1) return events;
      const chunkIndex = Math.max(1, Number(data.chunkIndex) || 1);
      const batchId =
        data.batchId ??
        `${messageType}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      let bucket = wsBatchBucketsRef.current.get(batchId);
      if (!bucket) {
        const timeoutId = window.setTimeout(() => {
          const timedOut = wsBatchBucketsRef.current.get(batchId);
          if (!timedOut) return;
          wsBatchBucketsRef.current.delete(batchId);
          if (timedOut.messageType === "initial_photos") {
            if (!initialLoadDoneRef.current) {
              applyInitialSnapshot(timedOut.events);
            }
          } else {
            enqueueWsEventsRef.current(timedOut.events);
          }
        }, WS_BATCH_FAILSAFE_MS);
        bucket = {
          messageType,
          totalChunks,
          receivedChunks: new Set<number>(),
          events: [],
          timeoutId,
        };
        wsBatchBucketsRef.current.set(batchId, bucket);
      }
      if (!bucket.receivedChunks.has(chunkIndex)) {
        bucket.receivedChunks.add(chunkIndex);
        bucket.events.push(...events);
      }
      if (bucket.receivedChunks.size >= bucket.totalChunks) {
        wsBatchBucketsRef.current.delete(batchId);
        window.clearTimeout(bucket.timeoutId);
        return bucket.events;
      }
      return null;
    },
    [applyInitialSnapshot],
  );

  const handleWebSocketMessage = useCallback(
    (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as PhotoWsMessage;
        if (data.type === "ping" || data.type === "heartbeat") return;
        const events = extractEventsFromMessage(data);

        if (data.type === "initial_photos" || data.type == null) {
          const snapshotEvents = collectChunkedEvents(
            "initial_photos",
            data,
            events,
          );
          if (snapshotEvents == null) return;
          applyInitialSnapshot(snapshotEvents);
          return;
        }

        if (data.type === "photos_updated") {
          const chunkEvents = collectChunkedEvents(
            "photos_updated",
            data,
            events,
          );
          if (chunkEvents == null) return;
          enqueueWsEvents(chunkEvents);
          return;
        }

        if (events.length > 0) {
          enqueueWsEvents(events);
        }
      } catch (error) {
        log.error("Error processing WebSocket message:", error);
      }
    },
    [
      applyInitialSnapshot,
      collectChunkedEvents,
      enqueueWsEvents,
      extractEventsFromMessage,
    ],
  );

  const wsUrl = useMemo(() => {
    const urlObj = new URL(apiUrl);
    const protocol = urlObj.protocol === "https:" ? "wss" : "ws";
    return `${protocol}://${urlObj.host}/ws/photos/?date=${date}&legacy=0&risk_only=0`;
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

  const clearWsRuntimeBuffers = useCallback(() => {
    if (wsMergeTimerRef.current != null) {
      window.clearTimeout(wsMergeTimerRef.current);
      wsMergeTimerRef.current = null;
    }
    wsMergeBufferRef.current = [];
    clearDelayedPhotoAttachTimers();

    const batchBuckets = wsBatchBucketsRef.current;
    batchBuckets.forEach((bucket) => {
      window.clearTimeout(bucket.timeoutId);
    });
    batchBuckets.clear();
  }, [clearDelayedPhotoAttachTimers]);

  useEffect(() => {
    return () => {
      clearWsRuntimeBuffers();
    };
  }, [clearWsRuntimeBuffers]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible" && !isConnected) {
        reconnect();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [isConnected, reconnect]);

  const riskPhotos = useMemo(
    () => photos.filter(isRiskPhotoCandidate),
    [photos],
  );
  const freshPhotos = useMemo(
    () => photos.slice(0, getMaxPhotos()),
    [photos, getMaxPhotos],
  );

  const displayPhotos = useMemo(() => {
    if (viewMode === "risk") {
      return riskPhotos;
    }
    if (viewMode === "all") {
      return photos;
    }
    return freshPhotos;
  }, [freshPhotos, photos, riskPhotos, viewMode]);
  const pendingFilterLabel = showRiskOnly
    ? "Обновляем ленту: только фото с рисками"
    : showAllPhotos
      ? "Обновляем ленту: все фото за день"
      : "Обновляем ленту: только свежие фото";
  const hasAnyPhotos = photos.length > 0;
  const hasDisplayPhotos = displayPhotos.length > 0;
  const shouldShowPendingFilterUi = isDisplayFilterPending && hasAnyPhotos;

  const toggleLabel = useMemo(() => {
    if (showRiskOnly) {
      return isDisplayFilterPending
        ? lastNonRiskViewMode === "all"
          ? "Все фото за день..."
          : "Только свежие..."
        : lastNonRiskViewMode === "all"
          ? `Все фото за день (риск: ${displayPhotos.length})`
          : `Только свежие (риск: ${displayPhotos.length})`;
    }
    if (showAllPhotos) {
      return "Все фото";
    }
    return isDisplayFilterPending
      ? "Только свежие..."
      : `Только свежие (${displayPhotos.length} из ${photos.length})`;
  }, [
    showRiskOnly,
    showAllPhotos,
    isDisplayFilterPending,
    lastNonRiskViewMode,
    displayPhotos.length,
    photos.length,
  ]);

  const riskToggleLabel = useMemo(
    () =>
      showRiskOnly
        ? "Риск: подозрительные / проверка / ошибка"
        : "Все статусы фото",
    [showRiskOnly],
  );
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
      if (isKioskMode && w >= 2560) {
        cardW = Math.min(cardW + 16, CARD_WIDTH_2XL + 20);
      } else if (isKioskMode && w >= 1920) {
        cardW = Math.min(cardW + 12, CARD_WIDTH_XL + 16);
      }

      const baseRows = getTapeNumRows(
        h,
        w,
        extraBottom,
        extraTop,
        headerReserve,
      );
      const isSingleRowLandscape = isSingleRowLandscapeViewport(w, h);
      const preferredRows = isKioskMode
        ? getPreferredRowsForViewport(w, h)
        : baseRows;
      const rows = isSingleRowLandscape
        ? 1
        : isKioskMode
          ? Math.max(baseRows, preferredRows)
          : baseRows;
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
    let layoutRafId: number | null = null;
    const scheduleLayoutUpdate = () => {
      if (layoutRafId !== null) return;
      layoutRafId = requestAnimationFrame(() => {
        layoutRafId = null;
        updateLayout();
      });
    };
    updateLayout();
    const el = containerRef.current;
    const hasResizeObserver = typeof window.ResizeObserver !== "undefined";
    let ro: ResizeObserver | null = null;
    if (hasResizeObserver) {
      ro = new ResizeObserver(scheduleLayoutUpdate);
      if (el) ro.observe(el);
    }
    window.addEventListener("resize", scheduleLayoutUpdate);
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", scheduleLayoutUpdate);
      window.visualViewport.addEventListener("scroll", scheduleLayoutUpdate);
    }
    document.addEventListener("fullscreenchange", scheduleLayoutUpdate);
    document.addEventListener("webkitfullscreenchange", scheduleLayoutUpdate);
    return () => {
      if (layoutRafId !== null) {
        cancelAnimationFrame(layoutRafId);
      }
      if (ro) {
        ro.disconnect();
      }
      window.removeEventListener("resize", scheduleLayoutUpdate);
      if (window.visualViewport) {
        window.visualViewport.removeEventListener(
          "resize",
          scheduleLayoutUpdate,
        );
        window.visualViewport.removeEventListener(
          "scroll",
          scheduleLayoutUpdate,
        );
      }
      document.removeEventListener("fullscreenchange", scheduleLayoutUpdate);
      document.removeEventListener(
        "webkitfullscreenchange",
        scheduleLayoutUpdate,
      );
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

  useEffect(() => {
    const touchActivity = () => {
      lastPointerActivityRef.current = Date.now();
    };
    window.addEventListener("mousemove", touchActivity, { passive: true });
    window.addEventListener("mousedown", touchActivity, { passive: true });
    window.addEventListener("wheel", touchActivity, { passive: true });
    window.addEventListener("touchstart", touchActivity, { passive: true });
    window.addEventListener("touchmove", touchActivity, { passive: true });
    return () => {
      window.removeEventListener("mousemove", touchActivity);
      window.removeEventListener("mousedown", touchActivity);
      window.removeEventListener("wheel", touchActivity);
      window.removeEventListener("touchstart", touchActivity);
      window.removeEventListener("touchmove", touchActivity);
    };
  }, []);

  useEffect(() => {
    if (!hoveredPhotoKey || selectedPhoto) return;
    const timerId = window.setInterval(() => {
      const inactiveMs = Date.now() - lastPointerActivityRef.current;
      if (inactiveMs < HOVER_IDLE_RESUME_MS) return;
      const hasHoveredCard = !!document.querySelector(".photo-item:hover");
      if (!hasHoveredCard) {
        setHoveredPhotoKey(null);
      }
    }, 300);

    return () => window.clearInterval(timerId);
  }, [hoveredPhotoKey, selectedPhoto]);

  useEffect(() => {
    if (!hoveredPhotoKey) return;
    const stillVisible = displayPhotos.some(
      (photo) => getPhotoIdentity(photo) === hoveredPhotoKey,
    );
    if (!stillVisible) {
      setHoveredPhotoKey(null);
    }
  }, [displayPhotos, hoveredPhotoKey]);

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

  const applySinglePhotoUpdate = useCallback(
    (incomingPhoto: PhotoData) => {
      mergeCanonicalPhotoEvents([
        {
          ...incomingPhoto,
          op: incomingPhoto.op ?? "updated",
          stateCode: incomingPhoto.stateCode ?? "UPDATED_META",
          versionTs: incomingPhoto.versionTs ?? timezoneIsoNow(),
        },
      ]);
    },
    [mergeCanonicalPhotoEvents],
  );

  const submitManualVerdict = useCallback(
    async (action: PhotoVerdictAction) => {
      const currentPhoto = selectedPhotoRef.current;
      if (!currentPhoto?.id) {
        return;
      }
      clearScheduledVerdictModalClose();
      setVerdictError("");
      setIsVerdictSubmitting(true);
      let verdictSucceeded = false;
      let scheduleSkipAutoClose = false;
      try {
        const response = await apiClient.post(
          `/lesson_attendance/${currentPhoto.id}/photo_verdict/`,
          { action },
        );
        const updatedCount = Number(response.data?.updated_count ?? 0);
        const skippedIds = Array.isArray(response.data?.skipped_ids)
          ? response.data.skipped_ids.map((id: unknown) => Number(id))
          : [];
        const skippedReasons = Array.isArray(response.data?.skipped_reasons)
          ? (response.data.skipped_reasons as { id: number; reason: string }[])
          : [];
        const updatedRecord = Array.isArray(response.data?.results)
          ? (response.data.results[0] as PhotoData | undefined)
          : undefined;
        if (updatedRecord) {
          applySinglePhotoUpdate(updatedRecord);
          setSelectedPhoto(updatedRecord);
          verdictSucceeded = true;
        } else if (updatedCount === 0 && skippedIds.includes(currentPhoto.id)) {
          const reasonEntry = skippedReasons.find(
            (r) => r.id === currentPhoto.id,
          );
          const reasonFromServer = reasonEntry?.reason ?? "unknown";
          console.warn("[PhotoVerdict] manual verdict unavailable", {
            photoId: currentPhoto.id,
            photoManualVerdict: currentPhoto.photoManualVerdict,
            photoSpoofStatus: currentPhoto.photoSpoofStatus,
            photoCanSetManualVerdict: currentPhoto.photoCanSetManualVerdict,
            reasonFromServer,
          });
          const reasonMessage: Record<string, string> = {
            no_photo: "Нет фото для проверки.",
            verdict_already_set: "Ручной вердикт уже выставлен.",
            status_not_reviewable:
              "Уже не требуется: запись обработана автоматически, ручной вердикт не нужен.",
            rescan_skipped_has_verdict:
              "Повторная проверка пропущена: уже есть ручной вердикт.",
          };
          const noticeText =
            reasonMessage[reasonFromServer] ??
            "Для этой записи ручной вердикт сейчас недоступен.";
          setVerdictSkipNotice(noticeText);
          scheduleSkipAutoClose = true;

          let refreshedRow: PhotoData | null = null;
          try {
            const refreshResp = await apiClient.get<{
              results?: PhotoData[];
            }>("/lesson_attendance/photo_verdicts/", {
              params: { id: currentPhoto.id },
            });
            const row = refreshResp.data?.results?.[0];
            if (row != null && row.id === currentPhoto.id) {
              refreshedRow = row;
            }
          } catch (refreshErr) {
            log.warn(
              "[PhotoVerdict] skip: не удалось подтянуть актуальную запись",
              refreshErr,
            );
          }
          if (refreshedRow) {
            applySinglePhotoUpdate(refreshedRow);
          } else {
            applySinglePhotoUpdate(
              buildVerdictSkipFallbackPatch(currentPhoto, reasonFromServer),
            );
          }
        } else if (updatedCount > 0) {
          verdictSucceeded = true;
        }
      } catch (error) {
        log.error("Failed to update manual photo verdict", error);
        console.error("[PhotoVerdict] submit failed", {
          photoId: currentPhoto?.id,
          action,
          error,
        });
        const responseError = error as {
          response?: {
            status?: number;
            data?: { detail?: string; error?: string };
          };
        };
        const statusCode = responseError.response?.status ?? 0;
        const detail = responseError.response?.data?.detail;
        const fallbackError = responseError.response?.data?.error;
        const serverMessage =
          (typeof detail === "string" && detail.trim()) ||
          (typeof fallbackError === "string" && fallbackError.trim()) ||
          "";
        if (statusCode === 401 || statusCode === 403) {
          setVerdictError(
            serverMessage ||
              "Нет доступа к сохранению. Обновите страницу и войдите заново.",
          );
        } else {
          setVerdictError(
            serverMessage || "Не удалось сохранить ручной вердикт.",
          );
        }
      } finally {
        setIsVerdictSubmitting(false);
        if (verdictSucceeded) {
          setVerdictAutoClosePending(true);
          const delayMs = prefersReducedMotion
            ? VERDICT_AUTO_CLOSE_DELAY_REDUCED_MS
            : VERDICT_AUTO_CLOSE_DELAY_MS;
          verdictCloseTimerRef.current = window.setTimeout(() => {
            verdictCloseTimerRef.current = null;
            setVerdictAutoClosePending(false);
            setVerdictSkipNotice("");
            setSelectedPhoto(null);
          }, delayMs);
        } else if (scheduleSkipAutoClose) {
          setVerdictAutoClosePending(true);
          const delayMs = prefersReducedMotion
            ? VERDICT_SKIP_MODAL_CLOSE_REDUCED_MS
            : VERDICT_SKIP_MODAL_CLOSE_MS;
          verdictCloseTimerRef.current = window.setTimeout(() => {
            verdictCloseTimerRef.current = null;
            setVerdictAutoClosePending(false);
            setVerdictSkipNotice("");
            setSelectedPhoto(null);
          }, delayMs);
        }
      }
    },
    [
      applySinglePhotoUpdate,
      clearScheduledVerdictModalClose,
      prefersReducedMotion,
    ],
  );

  const renderLoading = () => (
    <motion.div
      key="overlay-loader"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.22 }}
      className="fixed inset-0 z-40 flex items-center justify-center pointer-events-none"
    >
      <div className="relative pointer-events-auto">
        {/* Ambient glow blobs */}
        <div
          className="absolute rounded-full bg-primary-500/18 blur-3xl pointer-events-none"
          style={{
            inset: "-4rem",
            animation: "loaderGlowPulse 3.2s ease-in-out infinite",
          }}
        />
        <div
          className="absolute rounded-full bg-secondary-500/12 blur-2xl pointer-events-none"
          style={{
            inset: "-2.5rem",
            animation: "loaderGlowPulse 3.2s ease-in-out infinite",
            animationDelay: "1.6s",
          }}
        />
        {/* Frosted glass card */}
        <div className="relative rounded-[28px] border border-white/30 dark:border-white/10 bg-white/82 dark:bg-slate-900/82 backdrop-blur-2xl shadow-2xl shadow-primary-900/15 px-14 py-11 flex flex-col items-center gap-4">
          <LoaderComponent fullscreen={false} className="min-h-0" message="" />
          <p className="text-sm text-gray-500 dark:text-gray-400 tracking-wide">
            Загрузка посещаемости…
          </p>
        </div>
      </div>
    </motion.div>
  );

  const renderNoPhotos = useCallback(
    () => (
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
            Фотографий пока нет
          </h2>
          <p className="mt-2 text-center text-sm sm:text-base text-gray-600 dark:text-gray-300">
            За выбранный день ещё не пришло ни одной фотографии посещаемости.
          </p>
          <p className="mt-3 text-center text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            Оставьте страницу открытой: как только фотографии появятся, лента
            обновится автоматически.
          </p>
        </div>
      </motion.div>
    ),
    [],
  );

  const renderNoPhotosForFilter = useCallback(
    () => (
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
            По текущему фильтру пока нет фотографий
          </h2>
          <p className="mt-2 text-center text-sm sm:text-base text-gray-600 dark:text-gray-300">
            Сейчас нет фото со статусом «Подозрительное», «Проверить» или
            «Ошибка».
          </p>
          <p className="mt-3 text-center text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            {showAllPhotos
              ? "Отключите фильтр «Риск: подозрительные / проверка / ошибка», чтобы увидеть все записи за день."
              : "Отключите фильтр «Риск: подозрительные / проверка / ошибка», чтобы вернуться к свежим фото."}
          </p>
        </div>
      </motion.div>
    ),
    [showAllPhotos],
  );

  const renderEmptyStateCard = useCallback(() => {
    if (hasAnyPhotos) {
      return renderNoPhotosForFilter();
    }
    return renderNoPhotos();
  }, [hasAnyPhotos, renderNoPhotos, renderNoPhotosForFilter]);

  const renderFilterTransitionState = useCallback(
    () => (
      <motion.div
        className="py-16 sm:py-20"
        initial={{ opacity: 0, scale: 0.96, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 6 }}
        transition={{ type: "spring", damping: 26, stiffness: 300, mass: 0.85 }}
      >
        <div className="mx-auto w-full max-w-lg rounded-[28px] border border-white/20 dark:border-primary-400/20 bg-slate-900/45 dark:bg-slate-900/60 p-6 sm:p-7 shadow-[0_28px_80px_-28px_rgba(37,99,235,0.65)] backdrop-blur-2xl">
          <LoaderComponent
            fullscreen={false}
            compact
            inline
            variant="bars"
            className="min-h-0 justify-center text-slate-100 dark:text-primary-100"
            message={pendingFilterLabel}
          />
        </div>
      </motion.div>
    ),
    [pendingFilterLabel],
  );

  const photoRows = useMemo(() => {
    if (useStaticPhotoGridMode) {
      return [];
    }
    if (displayPhotos.length === 0) {
      return [];
    }
    const w = viewport.width;
    const h = viewport.height;
    const isSingleRowLandscape = isSingleRowLandscapeViewport(w, h);
    const isKioskMode = isKiosk || isFullscreen;
    const minCardsPerRow = isSingleRowLandscape
      ? Number.MAX_SAFE_INTEGER
      : isKioskMode && viewport.resolutionTier === "uhd"
        ? 6
        : isKioskMode && viewport.resolutionTier === "qhd"
          ? 7
          : isKioskMode
            ? 7
            : 5;
    const maxRowsByDensity = Math.max(
      1,
      Math.floor(displayPhotos.length / minCardsPerRow),
    );
    const numRows = isSingleRowLandscape
      ? 1
      : Math.max(1, Math.min(tapeNumRows, maxRowsByDensity));
    if (numRows <= 0) {
      return [];
    }

    const rows: PhotoData[][] = Array.from({ length: numRows }, () => []);
    const sticky = photoTapeRowByIdRef.current;
    const presentIds = new Set<number>();
    for (const p of displayPhotos) {
      if (p.id != null) presentIds.add(p.id);
    }
    for (const id of sticky.keys()) {
      if (!presentIds.has(id)) sticky.delete(id);
    }
    const rowLoad = Array(numRows).fill(0);
    const pickLeastLoadedRow = (): number => {
      let best = 0;
      let min = rowLoad[0];
      for (let i = 1; i < numRows; i += 1) {
        if (rowLoad[i] < min) {
          min = rowLoad[i];
          best = i;
        }
      }
      return best;
    };
    for (const photo of displayPhotos) {
      const id = photo.id;
      let rowIndex: number;
      if (id != null) {
        const prev = sticky.get(id);
        if (prev !== undefined && prev < numRows) {
          rowIndex = prev;
        } else {
          rowIndex = pickLeastLoadedRow();
          sticky.set(id, rowIndex);
        }
        rowLoad[rowIndex] += 1;
      } else {
        rowIndex = stableHash(getPhotoIdentity(photo, 0)) % numRows;
      }
      rows[rowIndex].push(photo);
    }

    return rows;
  }, [
    displayPhotos,
    tapeNumRows,
    useStaticPhotoGridMode,
    isKiosk,
    isFullscreen,
    viewport.width,
    viewport.height,
    viewport.resolutionTier,
  ]);

  const tapeCols = Math.ceil(displayPhotos.length / tapeNumRows) || 1;
  const marqueeSpeed = useMemo(
    () => MARQUEE_SPEED + Math.min(Math.max(tapeCols, 1), 10) * 2,
    [tapeCols],
  );

  const renderCardMeta = useCallback((photo: PhotoData) => {
    const departmentLabel = getLabelForDepartment(photo);
    const clamp2Lines: React.CSSProperties = {
      display: "-webkit-box",
      WebkitLineClamp: 2,
      WebkitBoxOrient: "vertical",
      overflow: "hidden",
    };
    const clamp1Line: React.CSSProperties = {
      display: "-webkit-box",
      WebkitLineClamp: 1,
      WebkitBoxOrient: "vertical",
      overflow: "hidden",
    };

    return (
      <div className="h-[112px] sm:h-[118px] px-3 py-2.5 sm:px-3.5 sm:py-3 flex flex-col">
        <h2
          className="min-h-[2.4rem] text-[13px] sm:text-[13.5px] font-semibold leading-[1.2] text-gray-800 dark:text-gray-100 tracking-[0.005em]"
          style={clamp2Lines}
        >
          {photo.staffFullName}
        </h2>
        <div className="mt-1.5 h-px w-full bg-gray-200 dark:bg-gray-600/40" />
        <div className="mt-1.5 min-h-[2.15rem] max-h-[2.15rem] flex items-start gap-1.5 min-w-0 text-gray-600 dark:text-gray-300">
          <FaBuilding className="w-3 h-3 opacity-80 shrink-0 mt-[0.15rem]" />
          <span className="min-w-0 leading-[1.2]">
            <span
              className="block text-[10px] sm:text-[10.5px] uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400"
              style={clamp1Line}
            >
              {departmentLabel}
            </span>
            <span
              className="block text-[11px] sm:text-[11.5px] leading-[1.15] text-gray-700 dark:text-gray-300"
              style={clamp2Lines}
            >
              {photo.department}
            </span>
          </span>
        </div>
        <p className="mt-auto pt-1 text-[12px] sm:text-[12.5px] text-gray-600 dark:text-gray-400 flex items-center gap-1.5 leading-none">
          <FaClock className="w-3 h-3 opacity-75 shrink-0" />
          <span className="tabular-nums">
            {formatTime(photo.attendanceTime)}
          </span>
        </p>
      </div>
    );
  }, []);

  const focusCardByCoords = useCallback((row: number, col: number) => {
    const key = `r${row}-i${col}`;
    const el = cardRefs.current.get(key);
    if (el) {
      el.focus();
    }
  }, []);

  const getNextCardCoords = useCallback(
    (row: number, col: number, key: string): { row: number; col: number } => {
      const rows = photoRows.length;
      if (rows === 0) return { row, col };
      const rowLen = photoRows[row]?.length ?? 0;

      if (key === "ArrowRight") {
        if (col + 1 < rowLen) return { row, col: col + 1 };
        const nextRow = (row + 1) % rows;
        return { row: nextRow, col: 0 };
      }

      if (key === "ArrowLeft") {
        if (col - 1 >= 0) return { row, col: col - 1 };
        const prevRow = (row - 1 + rows) % rows;
        const prevLen = photoRows[prevRow]?.length ?? 1;
        return { row: prevRow, col: Math.max(0, prevLen - 1) };
      }

      if (key === "ArrowDown") {
        const nextRow = (row + 1) % rows;
        const nextLen = photoRows[nextRow]?.length ?? 1;
        return { row: nextRow, col: Math.min(col, Math.max(0, nextLen - 1)) };
      }

      const prevRow = (row - 1 + rows) % rows;
      const prevLen = photoRows[prevRow]?.length ?? 1;
      return { row: prevRow, col: Math.min(col, Math.max(0, prevLen - 1)) };
    },
    [photoRows],
  );

  useEffect(() => {
    if (photoRows.length === 0) {
      setActiveCardCoords(null);
      setActivePhotoKey(null);
      return;
    }

    if (activePhotoKey) {
      for (let rowIndex = 0; rowIndex < photoRows.length; rowIndex += 1) {
        const colIndex = photoRows[rowIndex].findIndex(
          (photo) =>
            photo != null && getPhotoIdentity(photo) === activePhotoKey,
        );
        if (colIndex >= 0) {
          setActiveCardCoords((prev) => {
            if (prev && prev.row === rowIndex && prev.col === colIndex) {
              return prev;
            }
            return { row: rowIndex, col: colIndex };
          });
          return;
        }
      }
    }

    setActiveCardCoords((prev) => {
      if (!prev) return { row: 0, col: 0 };
      const row = Math.min(prev.row, photoRows.length - 1);
      const rowLen = photoRows[row]?.length ?? 0;
      if (rowLen <= 0) return { row: 0, col: 0 };
      const col = Math.min(prev.col, rowLen - 1);
      if (prev.row === row && prev.col === col) return prev;
      return { row, col };
    });
  }, [activePhotoKey, photoRows]);

  useEffect(() => {
    if (!activeCardCoords) return;
    const activePhoto = photoRows[activeCardCoords.row]?.[activeCardCoords.col];
    if (!activePhoto) return;
    const nextPhotoKey = getPhotoIdentity(activePhoto);
    setActivePhotoKey((prev) => (prev === nextPhotoKey ? prev : nextPhotoKey));
  }, [activeCardCoords, photoRows]);

  useEffect(() => {
    if (useStaticPhotoGridMode) {
      return;
    }
    const isTypingTarget = (target: EventTarget | null): boolean => {
      if (!(target instanceof HTMLElement)) return false;
      const tag = target.tagName.toLowerCase();
      return (
        target.isContentEditable ||
        tag === "input" ||
        tag === "textarea" ||
        tag === "select"
      );
    };

    const onGlobalKeyDown = (e: KeyboardEvent) => {
      if (selectedPhoto) return;
      if (isTypingTarget(e.target)) return;
      if (photoRows.length === 0) return;

      const hasArrow =
        e.key === "ArrowRight" ||
        e.key === "ArrowLeft" ||
        e.key === "ArrowDown" ||
        e.key === "ArrowUp";
      const hasOpenKey = e.key === "Enter" || e.key === " ";
      if (!hasArrow && !hasOpenKey) return;

      const current = activeCardCoords ?? { row: 0, col: 0 };
      if (hasArrow) {
        e.preventDefault();
        const next = getNextCardCoords(current.row, current.col, e.key);
        setActiveCardCoords((prev) =>
          prev?.row === next.row && prev?.col === next.col ? prev : next,
        );
        focusCardByCoords(next.row, next.col);
        return;
      }

      e.preventDefault();
      const rowPhoto = photoRows[current.row]?.[current.col];
      if (rowPhoto) {
        setSelectedPhoto(rowPhoto);
      }
    };

    window.addEventListener("keydown", onGlobalKeyDown);
    return () => window.removeEventListener("keydown", onGlobalKeyDown);
  }, [
    selectedPhoto,
    photoRows,
    activeCardCoords,
    getNextCardCoords,
    focusCardByCoords,
    useStaticPhotoGridMode,
  ]);

  const renderPhotoCard = useCallback(
    (
      photo: PhotoData,
      keyIndex: number,
      rowIndex: number,
      cardIndex: number,
      isInteractive: boolean,
      kioskCardWidth?: number,
      isClone = false,
      enableArrowNavigation = true,
      animationSurface: PhotoAnimationSurface = "grid",
      presenceMode: PhotoPresenceMode = "card",
    ) => {
      const photoIdentity = getPhotoIdentity(photo);
      const photoKey =
        photo.id != null ? photoIdentity : getPhotoIdentity(photo, keyIndex);
      const isActionableCard = isInteractive;
      const canTrackActiveCard =
        isActionableCard && enableArrowNavigation && !isClone;
      const uiStatus = resolvePhotoUiStatus(photo);
      const statusMeta = PHOTO_STATUS_STYLE[uiStatus];
      const getPresenceMotionProps = (
        surface: PhotoAnimationSurface,
        index: number,
        { useLayout = false }: { useLayout?: boolean } = {},
      ) => {
        if (surface === "marquee") {
          return { initial: false as const };
        }

        const enterDelay = prefersReducedMotion
          ? 0
          : Math.min(index, 6) * PHOTO_CARD_GRID_STAGGER_STEP;

        return {
          layout: useLayout ? ("position" as const) : undefined,
          initial: prefersReducedMotion
            ? { opacity: 0 }
            : {
                opacity: 0,
                y: 20,
                scale: 0.95,
              },
          animate: {
            opacity: 1,
            y: 0,
            scale: 1,
            transition: prefersReducedMotion
              ? { duration: 0.12 }
              : {
                  duration: 0.34,
                  delay: enterDelay,
                },
          },
          exit: prefersReducedMotion
            ? {
                opacity: 0,
                transition: { duration: 0.1 },
              }
            : {
                opacity: 0,
                y: -14,
                scale: 0.92,
                transition: {
                  duration: 0.2,
                },
              },
        };
      };
      const cardMotionProps =
        presenceMode === "card"
          ? getPresenceMotionProps(animationSurface, cardIndex, {
              useLayout:
                animationSurface === "grid" && !isClone && isActionableCard,
            })
          : { initial: false as const };
      const cardBody = (
        <div className="w-full flex-1 flex flex-col min-h-0 overflow-hidden rounded-2xl bg-white dark:bg-gray-800">
          <div className="relative w-full aspect-square flex items-center justify-center overflow-hidden bg-gradient-to-br from-gray-100 via-white to-gray-200 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
            {statusMeta.showBadgeOnCard && (
              <div
                className={`absolute left-2 top-2 z-20 inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-semibold shadow backdrop-blur-sm ${statusMeta.badgeClass}`}
              >
                <FaShieldAlt className="h-3 w-3" />
                <span>{statusMeta.label}</span>
              </div>
            )}
            <PhotoCardImage photo={photo} isClone={isClone} />
          </div>
          {renderCardMeta(photo)}
        </div>
      );

      if (!isActionableCard) {
        return (
          <motion.article
            key={photoKey}
            {...cardMotionProps}
            className={`photo-item group relative flex-shrink-0 w-[220px] sm:w-[260px] md:w-[280px] lg:w-[300px] rounded-2xl md:rounded-3xl select-none flex flex-col transition-shadow duration-300 overflow-hidden bg-white/95 dark:bg-gray-800/95 ring-1 ring-white/80 dark:ring-gray-700/90 shadow-[0_12px_30px_-20px_rgba(15,23,42,0.7)] ${statusMeta.cardClass}`}
            style={
              kioskCardWidth != null ? { width: kioskCardWidth } : undefined
            }
            aria-hidden
          >
            {cardBody}
          </motion.article>
        );
      }

      return (
        <motion.article
          key={photoKey}
          {...cardMotionProps}
          className={`photo-item group relative flex-shrink-0 w-[220px] sm:w-[260px] md:w-[280px] lg:w-[300px] rounded-2xl md:rounded-3xl cursor-pointer select-none focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/60 focus-visible:ring-offset-2 flex flex-col transition-shadow duration-300 overflow-hidden bg-white/95 dark:bg-gray-800/95 ring-1 ring-white/80 dark:ring-gray-700/90 shadow-[0_12px_30px_-20px_rgba(15,23,42,0.7)] hover:shadow-[0_20px_45px_-25px_rgba(37,99,235,0.55)] hover:ring-primary-300/70 dark:hover:ring-primary-400/45 ${statusMeta.cardClass}`}
          style={kioskCardWidth != null ? { width: kioskCardWidth } : undefined}
          onClick={() => setSelectedPhoto(photo)}
          onMouseEnter={() => setHoveredPhotoKey(photoIdentity)}
          onMouseLeave={() => setHoveredPhotoKey(null)}
          onTouchStart={() => setHoveredPhotoKey(photoIdentity)}
          onTouchEnd={() => setHoveredPhotoKey(null)}
          onFocus={() => {
            setHoveredPhotoKey(photoIdentity);
            if (canTrackActiveCard) {
              setActiveCardCoords((prev) =>
                prev?.row === rowIndex && prev?.col === cardIndex
                  ? prev
                  : { row: rowIndex, col: cardIndex },
              );
              setActivePhotoKey(photoIdentity);
            }
          }}
          onBlur={() =>
            setHoveredPhotoKey((prev) => (prev === photoIdentity ? null : prev))
          }
          onMouseMove={() => {
            if (canTrackActiveCard) {
              setActiveCardCoords((prev) =>
                prev?.row === rowIndex && prev?.col === cardIndex
                  ? prev
                  : { row: rowIndex, col: cardIndex },
              );
              setActivePhotoKey(photoIdentity);
            }
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setSelectedPhoto(photo);
              return;
            }
            if (!enableArrowNavigation) {
              return;
            }
            if (
              e.key !== "ArrowRight" &&
              e.key !== "ArrowLeft" &&
              e.key !== "ArrowDown" &&
              e.key !== "ArrowUp"
            ) {
              return;
            }
            e.preventDefault();
            const next = getNextCardCoords(rowIndex, cardIndex, e.key);
            focusCardByCoords(next.row, next.col);
          }}
          role="button"
          tabIndex={0}
          aria-hidden={undefined}
          aria-label={`${photo.staffFullName}, ${photo.department}`}
          ref={(el) => {
            const key = `r${rowIndex}-i${cardIndex}`;
            if (canTrackActiveCard) {
              cardRefs.current.set(key, el);
            } else {
              cardRefs.current.delete(key);
            }
          }}
          {...(animationSurface === "marquee" || prefersReducedMotion
            ? {
                transition: { duration: 0.18 },
              }
            : {
                whileHover: { y: -5 },
                whileTap: { scale: 0.975 },
                transition: {
                  type: "spring" as const,
                  damping: 22,
                  stiffness: 340,
                  mass: 0.75,
                },
              })}
        >
          {cardBody}
        </motion.article>
      );
    },
    [
      renderCardMeta,
      focusCardByCoords,
      getNextCardCoords,
      prefersReducedMotion,
    ],
  );

  const isMarqueePaused =
    !useStaticPhotoGridMode &&
    (!!selectedPhoto ||
      !!hoveredPhotoKey ||
      isDisplayFilterPending ||
      !isPageVisible);

  const renderPhotos = () => (
    <div
      className={
        isKiosk ? "min-h-[100dvh] flex flex-col py-3 sm:py-4 md:py-5" : "py-6"
      }
    >
      {displayPhotos.length > 0 && hints && !isKiosk && (
        <p className="text-gray-500 dark:text-gray-400 text-xs sm:text-sm mb-3">
          {hints}
        </p>
      )}
      <div
        className={`mx-auto w-full max-w-[1500px] flex-shrink-0 relative ${
          isFullscreen
            ? "mb-1.5 rounded-xl border border-white/55 dark:border-slate-700/70 bg-white/65 dark:bg-slate-900/45 backdrop-blur-md px-2 py-1.5 shadow-lg lg:mb-4 lg:rounded-2xl lg:px-5 lg:py-3"
            : isKiosk
              ? "mb-1.5 px-2 py-1 lg:mb-4 lg:px-5 lg:py-2"
              : "mb-4"
        }`}
      >
        {isFullscreen || isKiosk ? (
          <div className="flex flex-col gap-3 min-w-0 lg:flex-row lg:items-center lg:justify-between lg:gap-4">
            <div className="min-w-0 flex-1">
              <h1 className="font-semibold text-gray-800 dark:text-white truncate text-sm sm:text-base lg:text-xl xl:text-2xl">
                {pageTitle}
              </h1>
              <p className="text-gray-600 dark:text-gray-300 mt-0 text-[10px] sm:text-xs lg:text-sm">
                {pageSubtitle}
              </p>
            </div>
            <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-2 sm:gap-y-2 lg:gap-4 lg:shrink-0">
              {(photos.length > 0 || showRiskOnly) && (
                <Toggle
                  checked={showRiskOnly}
                  onChange={handleRiskOnlyToggleChange}
                  labelPosition="left"
                  label={riskToggleLabel}
                  ariaLabel={
                    showRiskOnly
                      ? "Показывать все статусы фото"
                      : "Показывать требующие проверки"
                  }
                  variant="rose"
                  className="!flex w-full min-w-0 justify-between gap-2 text-[10px] sm:!inline-flex sm:w-auto sm:justify-start sm:text-xs sm:gap-3 lg:text-sm"
                  labelClassName="min-w-0 flex-1 text-left leading-snug sm:flex-none"
                />
              )}
              {photos.length > 0 && (
                <Toggle
                  checked={showAllPhotos}
                  onChange={handleShowAllPhotosToggleChange}
                  disabled={showRiskOnly}
                  labelPosition="left"
                  label={toggleLabel}
                  ariaLabel={
                    showAllPhotos
                      ? "Показать только последние фото"
                      : "Показать все фото за день"
                  }
                  className="!flex w-full min-w-0 justify-between gap-2 text-[10px] sm:!inline-flex sm:w-auto sm:justify-start sm:text-xs sm:gap-3 lg:text-sm"
                  labelClassName="min-w-0 flex-1 text-left leading-snug sm:flex-none"
                />
              )}
              <motion.button
                onClick={handleFullscreenToggle}
                disabled={isFullscreenBusy}
                className={`flex w-full shrink-0 items-center justify-center gap-1 rounded-lg font-semibold text-white transition-colors px-2 py-1 text-xs sm:w-auto sm:justify-start lg:gap-2 lg:px-4 lg:py-2 lg:text-sm ${
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
                  <FaCompress className="w-3.5 h-3.5 lg:w-4 lg:h-4" />
                ) : (
                  <FaExpand className="w-3.5 h-3.5 lg:w-4 lg:h-4" />
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
              <EditableDateField
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                displayLabel={todayLabel}
                isLoading={loading}
                ariaLabel="Изменить дату показа"
                startIcon={
                  <FaRegCalendarAlt className="opacity-80 w-3 h-3 lg:w-4 lg:h-4 shrink-0" />
                }
                containerClassName="w-full shrink-0 sm:w-auto"
                displayClassName="inline-flex w-full items-center justify-center gap-1 rounded-lg border border-white/50 dark:border-slate-700/80 bg-white/55 dark:bg-slate-900/55 text-gray-600 dark:text-gray-300 whitespace-nowrap px-2 py-1 text-[10px] sm:w-auto sm:justify-start sm:text-xs lg:gap-2 lg:px-4 lg:py-2 lg:text-base hover:bg-white/75 dark:hover:bg-slate-800/70 transition-colors capitalize cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              />
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-2 sm:gap-3">
            <div className="flex flex-col gap-2 min-w-0 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
              <div className="min-w-0 flex-1">
                <h1 className="text-lg sm:text-xl md:text-2xl font-semibold text-gray-800 dark:text-white truncate">
                  {pageTitle}
                </h1>
                <p className="mt-0.5 text-[11px] sm:text-xs md:text-sm text-gray-600 dark:text-gray-300">
                  {pageSubtitle}
                </p>
              </div>
              <EditableDateField
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                displayLabel={todayLabel}
                isLoading={loading}
                ariaLabel="Изменить дату показа"
                startIcon={
                  <FaRegCalendarAlt className="w-3.5 h-3.5 md:w-4 md:h-4 opacity-80 shrink-0" />
                }
                containerClassName="w-full shrink-0 sm:w-auto"
                displayClassName="inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-white/50 dark:border-slate-700/80 bg-white/55 dark:bg-slate-900/55 text-gray-600 dark:text-gray-300 whitespace-nowrap px-2.5 py-1.5 text-xs sm:w-auto sm:justify-start sm:gap-2 sm:px-3 sm:text-sm md:px-4 md:py-2 md:text-base hover:bg-white/75 dark:hover:bg-slate-800/70 transition-colors capitalize cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              />
            </div>
            <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-3 md:gap-4">
              <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-3 sm:gap-y-2 md:gap-4">
                {(photos.length > 0 || showRiskOnly) && (
                  <Toggle
                    checked={showRiskOnly}
                    onChange={handleRiskOnlyToggleChange}
                    labelPosition="left"
                    label={riskToggleLabel}
                    ariaLabel={
                      showRiskOnly
                        ? "Показывать все статусы фото"
                        : "Показывать требующие проверки"
                    }
                    variant="rose"
                    className="!flex w-full min-w-0 justify-between gap-2 text-xs sm:!inline-flex sm:w-auto sm:justify-start sm:gap-3 sm:text-sm"
                    labelClassName="min-w-0 flex-1 text-left leading-snug sm:flex-none"
                  />
                )}
                {photos.length > 0 && (photos.length > 0 || showRiskOnly) && (
                  <div
                    className="hidden h-4 w-px shrink-0 bg-gray-200 dark:bg-gray-700 sm:block"
                    aria-hidden
                  />
                )}
                {photos.length > 0 && (
                  <Toggle
                    checked={showAllPhotos}
                    onChange={handleShowAllPhotosToggleChange}
                    disabled={showRiskOnly}
                    labelPosition="left"
                    label={toggleLabel}
                    ariaLabel={
                      showAllPhotos
                        ? "Показать только последние фото"
                        : "Показать все фото за день"
                    }
                    className="!flex w-full min-w-0 justify-between gap-2 text-xs sm:!inline-flex sm:w-auto sm:justify-start sm:gap-3 sm:text-sm"
                    labelClassName="min-w-0 flex-1 text-left leading-snug sm:flex-none"
                  />
                )}
              </div>
              <motion.button
                onClick={handleFullscreenToggle}
                disabled={isFullscreenBusy}
                className={`flex w-full shrink-0 items-center justify-center gap-2 rounded-lg font-semibold text-white transition-colors px-3.5 py-1.5 text-xs sm:ml-auto sm:w-auto sm:px-3.5 md:px-4 md:py-2 md:text-sm ${
                  isFullscreenBusy
                    ? "bg-primary-400 cursor-not-allowed"
                    : "bg-primary-600 hover:bg-primary-700"
                }`}
                aria-label="Полноэкранный режим"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <FaExpand className="w-4 h-4" />
                <span>{isFullscreenBusy ? "Открытие…" : "Полный экран"}</span>
              </motion.button>
            </div>
          </div>
        )}
        <AnimatePresence initial={false}>
          {shouldShowPendingFilterUi && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="z-30 mt-2 flex w-full justify-start sm:justify-center pointer-events-none"
              role="status"
              aria-live="polite"
              aria-label={pendingFilterLabel}
            >
              <div className="pointer-events-auto w-full max-w-md rounded-2xl border border-slate-200/90 bg-white px-3.5 py-2.5 shadow-md ring-1 ring-slate-200/80 dark:border-slate-600 dark:bg-slate-800 dark:ring-slate-600/80 sm:mx-auto">
                <LoaderComponent
                  fullscreen={false}
                  compact
                  inline
                  variant="bars"
                  showGlow={false}
                  className="min-h-0 justify-start gap-3"
                  message={pendingFilterLabel}
                  messageClassName="min-w-0 flex-1 text-left font-medium text-slate-900 dark:text-slate-50"
                />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="relative min-h-0">
        {!hasDisplayPhotos ? (
          loading ? null : (
            <div className="mx-auto w-full max-w-[1700px] flex-1 min-h-0 px-4 sm:px-6 md:px-8 lg:px-10 pb-4 sm:pb-5 md:pb-6">
              {shouldShowPendingFilterUi
                ? renderFilterTransitionState()
                : renderEmptyStateCard()}
            </div>
          )
        ) : useStaticPhotoGridMode ? (
          <div
            ref={containerRef}
            className="mx-auto w-full max-w-[1700px] flex-1 min-h-0 px-4 sm:px-6 md:px-8 lg:px-10 pb-4 sm:pb-5 md:pb-6"
            style={{
              paddingBottom: "max(1rem, env(safe-area-inset-bottom, 0px))",
            }}
          >
            <div
              className={
                isKiosk || isFullscreen
                  ? "h-full overflow-y-auto overflow-x-hidden pr-1 [scrollbar-width:thin]"
                  : "overflow-visible"
              }
            >
              <div
                className="flex flex-wrap items-start justify-center gap-3 sm:gap-4 md:gap-5 py-2 sm:py-3 md:py-4"
                onMouseLeave={() => setHoveredPhotoKey(null)}
              >
                <AnimatePresence initial={false} mode="popLayout">
                  {displayPhotos.map((photo, index) =>
                    renderPhotoCard(
                      photo,
                      index,
                      0,
                      index,
                      true,
                      kioskNarrowViewport ? cardWidthPx : undefined,
                      false,
                      false,
                      "grid",
                      "card",
                    ),
                  )}
                </AnimatePresence>
              </div>
            </div>
          </div>
        ) : (
          <div
            className={`photo-marquee-lux-edges ${
              isKiosk || isFullscreen ? "photo-marquee-lux-edges-kiosk" : ""
            }`}
          >
            <div
              ref={containerRef}
              className={`[scrollbar-width:none] [-ms-overflow-style:none] ${
                isKiosk
                  ? "photo-kiosk-marquee-mask flex-1 min-h-0 flex flex-col overflow-x-hidden overflow-y-hidden px-4 sm:px-6 md:px-8 lg:px-10 py-2 sm:py-3 md:py-4 pb-4 sm:pb-5 md:pb-6"
                  : "overflow-x-hidden overflow-y-hidden py-4 pb-8 px-4 md:px-6"
              }`}
              style={
                isKiosk
                  ? {
                      paddingBottom:
                        "max(1rem, env(safe-area-inset-bottom, 0px))",
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
                        ? "overflow-x-hidden overflow-y-hidden py-2 sm:py-3 md:py-4 lg:py-5"
                        : "overflow-x-hidden overflow-y-hidden py-4 md:py-5"
                    }
                    style={{ minHeight: 1 }}
                    onMouseLeave={() => setHoveredPhotoKey(null)}
                  >
                    <MarqueeTrack
                      items={rowPhotos}
                      rowIndex={rowIndex}
                      speedPxSec={marqueeSpeed}
                      isPaused={isMarqueePaused}
                      hoverSpeed={MARQUEE_HOVER_SPEED}
                      cardWidthPx={cardWidthPx}
                      forceLoop={!isFreshMode}
                      renderItem={(
                        photo,
                        displayIndex,
                        copyIndex,
                        itemIndex,
                      ) => {
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
                          rowIndex * 1_000_000 +
                          copyIndex * 10_000 +
                          displayIndex;
                        const cardIndex = itemIndex;
                        return renderPhotoCard(
                          photo,
                          keyIndex,
                          rowIndex,
                          cardIndex,
                          true,
                          kioskNarrowViewport ? cardWidthPx : undefined,
                          copyIndex > 0,
                          true,
                          "marquee",
                          "wrapper",
                        );
                      }}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  const renderSelectedPhoto = () => {
    const lightboxBackdropTransition = prefersReducedMotion
      ? { duration: 0.12 }
      : { duration: 0.32, ease: [0.4, 0, 0.2, 1] as const };
    const lightboxModalTransition = prefersReducedMotion
      ? { duration: 0.18 }
      : { type: "spring" as const, damping: 30, stiffness: 320, mass: 0.85 };
    const lightboxModalExit = prefersReducedMotion
      ? { opacity: 0 }
      : { scale: 0.9, opacity: 0, y: 18 };

    return (
      <AnimatePresence initial={false}>
        {selectedPhoto && (
          <motion.div
            key={selectedPhoto.id}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 sm:p-5 md:p-6"
            onClick={() => setSelectedPhoto(null)}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={lightboxBackdropTransition}
          >
            <motion.div
              className="relative w-full max-w-md sm:max-w-lg md:max-w-xl lg:max-w-2xl rounded-2xl md:rounded-3xl overflow-hidden bg-white dark:bg-gray-800 shadow-2xl flex flex-col max-h-[90vh] md:max-h-[85vh] [@media(orientation:landscape)]:max-w-4xl [@media(orientation:landscape)]:max-h-[90vh]"
              onClick={(e) => e.stopPropagation()}
              initial={{ scale: 0.92, opacity: 0, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={lightboxModalExit}
              transition={lightboxModalTransition}
            >
              <button
                type="button"
                className="absolute top-3 right-3 z-10 w-9 h-9 md:w-10 md:h-10 rounded-full bg-white/90 dark:bg-gray-700/90 hover:bg-gray-100 dark:hover:bg-gray-600 shadow-md text-gray-700 dark:text-gray-200 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-primary-500 touch-manipulation transition-colors"
                onClick={() => setSelectedPhoto(null)}
                aria-label="Закрыть"
              >
                <FaTimes className="w-4 h-4 md:w-5 md:h-5" />
              </button>

              {(() => {
                const p = selectedPhoto;
                const uiStatus = resolvePhotoUiStatus(p);
                const statusMeta = PHOTO_STATUS_STYLE[uiStatus];
                const isSuspicious =
                  uiStatus === "suspicious_auto" ||
                  uiStatus === "suspicious_manual";
                const showCheckBadge =
                  uiStatus === "check" || uiStatus === "check_error";
                const manualVerdict: PhotoManualVerdict =
                  p.photoManualVerdict ?? "none";
                const canSetManualVerdict = isManualReviewRequiredByBackend(p);
                const verdictButtonsLocked =
                  isVerdictSubmitting || verdictAutoClosePending;

                return (
                  <div className="flex flex-col flex-1 min-h-0 overflow-y-auto overflow-x-hidden overscroll-contain [@media(orientation:landscape)]:flex-row [@media(orientation:landscape)]:overflow-hidden">
                    <div className="relative w-full aspect-square flex items-center justify-center overflow-hidden bg-gradient-to-br from-gray-100 via-white to-gray-200 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 flex-shrink-0 max-h-[50vh] [@media(orientation:landscape)]:max-h-none [@media(orientation:landscape)]:w-[min(42%,85vh)] [@media(orientation:landscape)]:min-w-0 [@media(orientation:landscape)]:aspect-square [@media(orientation:landscape)]:shrink-0">
                      <PhotoImageAsset
                        photo={p}
                        imageClassName="w-full h-full object-contain"
                        placeholderContainerClassName="w-full h-full flex flex-col items-center justify-center gap-3 bg-gradient-to-br from-slate-100/95 via-white to-slate-200/95 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900"
                        placeholderIconWrapperClassName="flex h-20 w-20 items-center justify-center rounded-3xl bg-slate-900/10 text-slate-600 dark:bg-slate-100/10 dark:text-slate-200"
                        placeholderIconClassName="h-10 w-10"
                        placeholderLabelClassName="inline-flex items-center rounded-full bg-black/60 px-3 py-1.5 text-xs font-medium text-white shadow-md backdrop-blur-sm"
                      />
                    </div>

                    <div className="p-5 sm:p-6 md:p-7 flex flex-col gap-3 flex-shrink-0 [@media(orientation:landscape)]:flex-1 [@media(orientation:landscape)]:min-w-0 [@media(orientation:landscape)]:overflow-y-auto [@media(orientation:landscape)]:justify-center">
                      <h2 className="text-xl md:text-2xl font-semibold text-gray-800 dark:text-white pr-10 md:pr-12">
                        {p.staffFullName}
                      </h2>
                      <div className="flex flex-col gap-1.5 text-sm">
                        <p className="text-gray-600 dark:text-gray-300 flex items-center gap-2">
                          <FaBuilding className="w-3.5 h-3.5 shrink-0 opacity-80" />
                          <span>
                            <span className="font-medium text-gray-700 dark:text-gray-200">
                              {getLabelForDepartment(p)}:
                            </span>{" "}
                            {p.department}
                          </span>
                        </p>
                        <p className="text-gray-600 dark:text-gray-300 flex items-center gap-2">
                          <FaClock className="w-3.5 h-3.5 shrink-0 opacity-80" />
                          <span>
                            <span className="font-medium text-gray-700 dark:text-gray-200">
                              Время:
                            </span>{" "}
                            {formatTime(p.attendanceTime)}
                          </span>
                        </p>
                        {(isSuspicious || showCheckBadge) && (
                          <div className="mt-2 flex items-center gap-2">
                            <span
                              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${statusMeta.badgeClass}`}
                            >
                              <FaShieldAlt className="h-3.5 w-3.5" />
                              {statusMeta.label}
                            </span>
                          </div>
                        )}
                        {p.tutorInfo && (
                          <p className="text-gray-500 dark:text-gray-400 text-xs mt-1 leading-relaxed">
                            {p.tutorInfo}
                          </p>
                        )}
                        {canSetManualVerdict && (
                          <>
                            <div className="mt-4 flex flex-wrap items-center gap-2">
                              <button
                                type="button"
                                disabled={
                                  verdictButtonsLocked ||
                                  manualVerdict === "suspicious"
                                }
                                onClick={() =>
                                  void submitManualVerdict("manual_suspicious")
                                }
                                className="inline-flex items-center gap-1 rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-rose-50 transition-colors hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                Подозрительная
                              </button>
                              <button
                                type="button"
                                disabled={
                                  verdictButtonsLocked ||
                                  manualVerdict === "clean"
                                }
                                onClick={() =>
                                  void submitManualVerdict("manual_clean")
                                }
                                className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-emerald-50 transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                Подтвердить
                              </button>
                            </div>
                            {verdictError && (
                              <p className="text-xs text-rose-600 dark:text-rose-300">
                                {verdictError}
                              </p>
                            )}
                          </>
                        )}
                        {(verdictSkipNotice || verdictAutoClosePending) && (
                          <div
                            className="mt-3 flex flex-col gap-2.5"
                            role="region"
                            aria-label="Статус проверки"
                          >
                            {verdictSkipNotice ? (
                              <div
                                className="flex gap-3 rounded-xl border border-amber-200/80 bg-gradient-to-br from-amber-50 via-amber-50/80 to-orange-50/50 px-3.5 py-3 shadow-sm shadow-amber-900/5 dark:border-amber-400/20 dark:bg-gradient-to-br dark:from-amber-950/55 dark:via-amber-950/40 dark:to-orange-950/25 dark:shadow-none dark:ring-1 dark:ring-inset dark:ring-amber-400/10"
                                role="status"
                                aria-live="polite"
                              >
                                <FaInfoCircle
                                  className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400"
                                  aria-hidden
                                />
                                <p className="min-w-0 text-[13px] sm:text-sm leading-snug text-amber-950/95 dark:text-amber-50/95">
                                  {verdictSkipNotice}
                                </p>
                              </div>
                            ) : null}
                            {verdictAutoClosePending ? (
                              <div
                                className="flex gap-3 rounded-xl border border-emerald-200/80 bg-gradient-to-br from-emerald-50 via-emerald-50/80 to-teal-50/45 px-3.5 py-3 shadow-sm shadow-emerald-900/5 dark:border-emerald-400/20 dark:bg-gradient-to-br dark:from-emerald-950/50 dark:via-emerald-950/35 dark:to-teal-950/25 dark:shadow-none dark:ring-1 dark:ring-inset dark:ring-emerald-400/10"
                                role="status"
                                aria-live="polite"
                              >
                                <FaCheckCircle
                                  className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400"
                                  aria-hidden
                                />
                                <p className="min-w-0 text-[13px] sm:text-sm leading-snug text-emerald-950/90 dark:text-emerald-50/90">
                                  Сохранено. Карточка закроется автоматически…
                                </p>
                              </div>
                            ) : null}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })()}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    );
  };

  return (
    <div>
      {renderPhotos()}

      <AnimatePresence>{loading && renderLoading()}</AnimatePresence>

      {renderSelectedPhoto()}
    </div>
  );
};

export default PhotoDashboard;
