import React, {
  useEffect,
  useState,
  useCallback,
  useMemo,
  useRef,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Bar, Doughnut } from "react-chartjs-2";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import {
  Chart as ChartJS,
  registerables,
  TooltipItem,
  ChartData,
  Chart,
  Plugin,
  ChartEvent,
  ActiveElement,
} from "chart.js";
import { AttendanceStats } from "../schemas/IData";
import Notification from "../components/Notification";
import LoaderComponent from "../components/LoaderComponent";
import { motion } from "framer-motion";
import useWindowSize from "../hooks/useWindowSize";
import EditableDateField from "../components/EditableDateField";
import { FaCompress, FaExpand } from "react-icons/fa";
import { useAppSelector } from "../store/hooks";

ChartJS.register(...registerables);

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

type BarChartInstance = ChartJS<"bar", number[], string>;
type DoughnutChartInstance = ChartJS<"doughnut", number[], string>;
type DashboardChartInstance = BarChartInstance | DoughnutChartInstance;

const barDataLabelsPlugin: Plugin<"bar"> = {
  id: "barDataLabels",
  afterDatasetsDraw(chart: Chart<"bar">) {
    const ctx = chart.ctx;
    const meta = chart.getDatasetMeta(0);
    if (!meta?.data?.length) return;
    meta.data.forEach((bar, i) => {
      const value = Number(chart.data.datasets[0]?.data?.[i] ?? 0);
      const displayText = value > 0 ? String(value) : "";
      const el = bar as {
        x?: number;
        y?: number;
        base?: number;
        width?: number;
        height?: number;
      };
      const midX = el.x ?? 0;
      const topY = Math.min(el.y ?? 0, el.base ?? 0) - 6;
      ctx.save();
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      ctx.font = "600 12px system-ui, sans-serif";
      ctx.fillStyle =
        (chart.options.plugins as { barDataLabels?: { color?: string } })
          ?.barDataLabels?.color ??
        (document.documentElement.classList.contains("dark")
          ? "rgba(209, 213, 219, 0.95)"
          : "rgba(55, 65, 81, 0.9)");
      ctx.fillText(displayText, midX, topY);
      ctx.restore();
    });
  },
};
ChartJS.register(barDataLabelsPlugin);

const doughnutActiveHighlightPlugin: Plugin<"doughnut"> = {
  id: "doughnutActiveHighlight",
  afterDatasetsDraw(chart: Chart<"doughnut">) {
    const active =
      chart.tooltip?.getActiveElements?.() ?? chart.getActiveElements();
    if (active.length === 0) return;
    const meta = chart.getDatasetMeta(0);
    if (!meta?.data?.length) return;
    const ctx = chart.ctx;
    active.forEach((a) => {
      const el = meta.data[a.index] as {
        x?: number;
        y?: number;
        outerRadius?: number;
        innerRadius?: number;
        startAngle?: number;
        endAngle?: number;
      };
      if (!el) return;
      const x = el.x ?? 0;
      const y = el.y ?? 0;
      const or = (el.outerRadius ?? 0) + 4;
      const ir = (el.innerRadius ?? 0) - 2;
      const sa = (el.startAngle ?? 0) - 0.02;
      const ea = (el.endAngle ?? 0) + 0.02;
      ctx.save();
      ctx.beginPath();
      ctx.arc(x, y, or, sa, ea);
      ctx.arc(x, y, ir, ea, sa, true);
      ctx.closePath();
      ctx.strokeStyle = "rgba(59, 130, 246, 0.9)";
      ctx.lineWidth = 3;
      ctx.stroke();
      ctx.restore();
    });
  },
};
ChartJS.register(doughnutActiveHighlightPlugin);

const STATS_CACHE_TTL_MS = 6 * 60 * 60 * 1000;

const statsCache = new Map<
  string,
  { data: AttendanceStats; expiresAt: number }
>();

function getStatsCacheKey(date: string, pin?: string): string {
  return `stats_${date}_${pin ?? "all"}`;
}

function getCachedStats(date: string, pin?: string): AttendanceStats | null {
  const key = getStatsCacheKey(date, pin);
  const entry = statsCache.get(key);
  if (!entry || Date.now() > entry.expiresAt) return null;
  return entry.data;
}

function setCachedStats(
  date: string,
  pin: string | undefined,
  data: AttendanceStats,
): void {
  const key = getStatsCacheKey(date, pin);
  statsCache.set(key, {
    data,
    expiresAt: Date.now() + STATS_CACHE_TTL_MS,
  });
}

const Dashboard: React.FC<{ pin?: string }> = ({ pin }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const isKiosk = new URLSearchParams(location.search).get("kiosk") === "1";
  const initialDate = (() => {
    const date = new Date();
    date.setDate(date.getDate() - 1);
    return date.toISOString().split("T")[0];
  })();

  const [selectedDate, setSelectedDate] = useState<string>(initialDate);
  const [stats, setStats] = useState<AttendanceStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [dateMismatchFromBackend, setDateMismatchFromBackend] = useState<
    string | null
  >(null);
  const requestedDateRef = useRef<string | null>(null);
  const { width, height } = useWindowSize();

  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [isFullscreenBusy, setIsFullscreenBusy] = useState<boolean>(false);
  const [hoveredLegendIndex, setHoveredLegendIndex] = useState<number | null>(
    null,
  );
  const [selectedLegendIndex, setSelectedLegendIndex] = useState<number | null>(
    null,
  );
  const diagramRef = useRef<HTMLDivElement>(null);
  const chartBarRef = useRef<BarChartInstance | null>(null);
  const chartDoughnutRef = useRef<DoughnutChartInstance | null>(null);
  const fullscreenToggleLockRef = useRef(false);
  const wasFullscreenRef = useRef(false);
  const reportsAutoRefreshMinutes = useAppSelector(
    (state) => state.ui.reportsAutoRefreshMinutes,
  );

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
    const handleFullscreenChange = () => {
      const nowFullscreen = !!getFullscreenElement();
      const prevFullscreen = wasFullscreenRef.current;
      wasFullscreenRef.current = nowFullscreen;

      setIsFullscreen(nowFullscreen);
      setIsFullscreenBusy(false);
      fullscreenToggleLockRef.current = false;

      if (prevFullscreen && !nowFullscreen) {
        if (new URLSearchParams(window.location.search).get("kiosk") === "1") {
          navigate(
            { pathname: location.pathname, search: "" },
            { replace: true },
          );
        }
      }
    };

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
  }, [getFullscreenElement, location.pathname, navigate]);

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
          await new Promise<void>((resolve) => window.setTimeout(resolve, 120));
        }

        const req =
          docEl.requestFullscreen ??
          docEl.webkitRequestFullscreen ??
          docEl.mozRequestFullScreen ??
          docEl.msRequestFullscreen;
        if (req) {
          await Promise.resolve(req.call(docEl));
        }
      } else {
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
    } catch (err) {
      console.error("Ошибка переключения полноэкранного режима:", err);
    } finally {
      window.setTimeout(() => {
        if (!getFullscreenElement()) {
          setIsFullscreenBusy(false);
          fullscreenToggleLockRef.current = false;
        }
      }, 360);
    }
  }, [getFullscreenElement, isKiosk, location.pathname, navigate]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "F11") {
        event.preventDefault();
        handleFullscreenToggle();
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [handleFullscreenToggle]);

  const getActiveChart = useCallback(
    (): DashboardChartInstance | null =>
      width < 768 ? chartDoughnutRef.current : chartBarRef.current,
    [width],
  );

  const syncChartActiveState = useCallback(
    (chart: DashboardChartInstance | null, index: number | null) => {
      if (!chart) return;
      const chartCanvas = chart.canvas;
      const chartCtx = (chart as { ctx?: unknown }).ctx;
      if (!chartCanvas || !chartCanvas.isConnected || !chartCtx) return;
      const isBarChart = chart === chartBarRef.current;

      if (typeof index === "number" && index >= 0) {
        const active = [{ datasetIndex: 0, index }];
        chart.setActiveElements(active);

        if (isBarChart) {
          chart.update("none");
          return;
        }

        const dataPoint = chart.getDatasetMeta(0)?.data?.[index] as
          | unknown
          | {
              x?: number;
              y?: number;
              tooltipPosition?: (useFinalPosition?: boolean) => {
                x: number;
                y: number;
              };
            };
        const fallback = { x: chart.width / 2, y: chart.height / 2 };
        const point = (
          dataPoint as {
            x?: number;
            y?: number;
            tooltipPosition?: (useFinalPosition?: boolean) => {
              x: number;
              y: number;
            };
          }
        )?.tooltipPosition?.(false) ?? {
          x: (dataPoint as { x?: number })?.x ?? fallback.x,
          y: (dataPoint as { y?: number })?.y ?? fallback.y,
        };
        chart.tooltip?.setActiveElements(active, point);
        chart.setActiveElements(active);
        chart.update("none");

        // Force native chart hover processing so tooltip is rendered on-canvas.
        const canvas = chart.canvas;
        if (canvas) {
          const rect = canvas.getBoundingClientRect();
          canvas.dispatchEvent(
            new MouseEvent("mousemove", {
              bubbles: true,
              clientX: rect.left + point.x,
              clientY: rect.top + point.y,
            }),
          );
        }
      } else {
        chart.setActiveElements([]);
        if (!isBarChart) {
          chart.tooltip?.setActiveElements([], { x: 0, y: 0 });
          chart.canvas?.dispatchEvent(
            new MouseEvent("mouseout", { bubbles: true }),
          );
        }
        chart.update("none");
      }
    },
    [],
  );

  const forceResizeCharts = useCallback(() => {
    const charts: DashboardChartInstance[] = [];
    if (chartBarRef.current) charts.push(chartBarRef.current);
    if (chartDoughnutRef.current) charts.push(chartDoughnutRef.current);

    charts.forEach((chart) => {
      const canvas = chart.canvas;
      const chartCtx = (chart as { ctx?: unknown }).ctx;
      if (!canvas || !canvas.isConnected || !chartCtx) return;
      try {
        chart.resize();
        chart.update("resize");
      } catch (error) {
        console.warn("Chart resize skipped due to transient state:", error);
      }
    });
  }, []);

  const scheduleChartResizeBurst = useCallback(() => {
    const runResize = () => {
      window.dispatchEvent(new Event("resize"));
      forceResizeCharts();
    };

    const rafId = requestAnimationFrame(runResize);
    const resizeDelays = [90, 180, 320, 520, 760, 1000, 1400];
    const timeouts = resizeDelays.map((delay) =>
      window.setTimeout(runResize, delay),
    );

    return () => {
      cancelAnimationFrame(rafId);
      timeouts.forEach((id) => window.clearTimeout(id));
    };
  }, [forceResizeCharts]);

  useEffect(() => {
    const el = diagramRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;

    let resizeTimeout: number | null = null;
    const ro = new ResizeObserver(() => {
      if (resizeTimeout !== null) {
        window.clearTimeout(resizeTimeout);
      }
      resizeTimeout = window.setTimeout(() => {
        const chart = getActiveChart();
        if (!chart) return;
        const canvas = chart.canvas;
        const chartCtx = (chart as { ctx?: unknown }).ctx;
        if (!canvas || !canvas.isConnected || !chartCtx) return;
        try {
          chart.resize();
          chart.update("resize");
        } catch (error) {
          console.warn(
            "Observed resize skipped due to transient state:",
            error,
          );
        }
      }, 90);
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      if (resizeTimeout !== null) {
        window.clearTimeout(resizeTimeout);
      }
    };
  }, [getActiveChart]);

  useEffect(() => {
    return scheduleChartResizeBurst();
  }, [scheduleChartResizeBurst, isFullscreen, isKiosk, width, height]);

  useEffect(() => {
    let cancelBurst: (() => void) | null = null;
    const onViewportMutation = () => {
      if (cancelBurst) {
        cancelBurst();
      }
      cancelBurst = scheduleChartResizeBurst();
    };

    window.addEventListener("orientationchange", onViewportMutation);
    document.addEventListener("fullscreenchange", onViewportMutation);
    document.addEventListener("webkitfullscreenchange", onViewportMutation);
    document.addEventListener("mozfullscreenchange", onViewportMutation);
    document.addEventListener("MSFullscreenChange", onViewportMutation);
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", onViewportMutation);
      window.visualViewport.addEventListener("scroll", onViewportMutation);
    }

    return () => {
      if (cancelBurst) {
        cancelBurst();
      }
      window.removeEventListener("orientationchange", onViewportMutation);
      document.removeEventListener("fullscreenchange", onViewportMutation);
      document.removeEventListener(
        "webkitfullscreenchange",
        onViewportMutation,
      );
      document.removeEventListener("mozfullscreenchange", onViewportMutation);
      document.removeEventListener("MSFullscreenChange", onViewportMutation);
      if (window.visualViewport) {
        window.visualViewport.removeEventListener("resize", onViewportMutation);
        window.visualViewport.removeEventListener("scroll", onViewportMutation);
      }
    };
  }, [scheduleChartResizeBurst]);

  const activeLegendIndex =
    selectedLegendIndex !== null ? selectedLegendIndex : hoveredLegendIndex;

  const applyLegendIndex = useCallback(
    (index: number | null) => {
      syncChartActiveState(getActiveChart(), index);
    },
    [getActiveChart, syncChartActiveState],
  );

  const handleLegendHover = useCallback(
    (index: number) => {
      setHoveredLegendIndex(index);
      applyLegendIndex(index);
    },
    [applyLegendIndex],
  );

  const handleLegendLeave = useCallback(() => {
    setHoveredLegendIndex(null);
    applyLegendIndex(selectedLegendIndex);
  }, [applyLegendIndex, selectedLegendIndex]);

  const handleLegendToggle = useCallback(
    (index: number) => {
      setHoveredLegendIndex(null);
      setSelectedLegendIndex((prev) => {
        const next = prev === index ? null : index;
        applyLegendIndex(next);
        return next;
      });
    },
    [applyLegendIndex],
  );

  useEffect(() => {
    const id = requestAnimationFrame(() => {
      const chart = getActiveChart();
      syncChartActiveState(chart, activeLegendIndex);
    });
    return () => cancelAnimationFrame(id);
  }, [activeLegendIndex, getActiveChart, syncChartActiveState, stats]);

  const fetchData = useCallback(async () => {
    const todayStr = new Date().toISOString().split("T")[0];
    if (selectedDate > todayStr) {
      setError("Выбранная дата не может быть в будущем");
      setLoading(false);
      return;
    }

    const cached = getCachedStats(selectedDate, pin);
    if (cached) {
      const safe = Array.isArray(cached.present_data)
        ? cached
        : { ...cached, present_data: [] };
      setSelectedDate(safe.data_for_date || selectedDate);
      setDateMismatchFromBackend(null);
      setStats(safe);
      setError(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    requestedDateRef.current = selectedDate;

    try {
      const params: { date: string; pin?: string } = { date: selectedDate };
      if (pin) params.pin = pin;

      const response = await axiosInstance.get(
        `${apiUrl}/api/attendance/stats/`,
        { params },
      );
      const data = response.data as AttendanceStats;
      if (!Array.isArray(data.present_data)) {
        data.present_data = [];
      }
      const backendDate = data.data_for_date || selectedDate;
      setSelectedDate(backendDate);
      if (
        data.data_for_date &&
        requestedDateRef.current !== null &&
        data.data_for_date !== requestedDateRef.current
      ) {
        setDateMismatchFromBackend(
          `Запрошена дата ${requestedDateRef.current}, сервер вернул данные за ${data.data_for_date} — отображаем по ответу сервера.`,
        );
      } else {
        setDateMismatchFromBackend(null);
      }
      setStats(data);
      setCachedStats(selectedDate, pin, data);
    } catch (err) {
      console.error(err);
      setError("Ошибка при загрузке данных. Пожалуйста, попробуйте позже.");
    } finally {
      setLoading(false);
    }
  }, [selectedDate, pin]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (reportsAutoRefreshMinutes <= 0) return;
    const intervalMs = reportsAutoRefreshMinutes * 60 * 1000;
    const id = window.setInterval(fetchData, intervalMs);
    return () => clearInterval(id);
  }, [fetchData, reportsAutoRefreshMinutes]);

  useEffect(() => {
    if (!loading && !stats && !error) {
      const timeout = setTimeout(() => {
        setError("Данные не были найдены.");
      }, 5000);
      return () => clearTimeout(timeout);
    }
  }, [loading, stats, error]);

  const formatDate = (dateString: string) => {
    const options: Intl.DateTimeFormatOptions = {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    };
    return new Date(dateString).toLocaleDateString("ru-RU", options);
  };

  const chartData = useMemo(() => {
    if (!stats) return null;

    const absentCount =
      stats.absent_staff_count ?? stats.absent_data?.length ?? 0;

    const filtered = stats.present_data
      .map((s) => ({
        ...s,
        individual_percentage: Math.ceil(s.individual_percentage),
      }))
      .filter(
        (s) =>
          s.individual_percentage >= 5 &&
          !["s99999999", "s99999999998"].includes(s.staff_pin),
      );

    const totalPresent = filtered.length;
    const totalWithAbsent = totalPresent + absentCount;

    let labels: string[];
    let counts: number[];
    let maxPct: number;
    let avg: number;
    let median: number;

    if (totalPresent === 0 && absentCount === 0) {
      return {
        labels: [],
        counts: [],
        maxPct: 0,
        totalPeople: 0,
        totalWithAbsent: 0,
        avg: 0,
        median: 0,
        niceStep: 1,
        barData: { labels: [], datasets: [] },
      };
    }

    const showAbsentColumn = absentCount > 0;
    const ABSENT_LABEL = "Отсутствовали";

    if (totalPresent === 0) {
      labels = showAbsentColumn ? [ABSENT_LABEL] : [];
      counts = showAbsentColumn ? [absentCount] : [];
      maxPct = 0;
      avg = 0;
      median = 0;
    } else {
      maxPct = Math.max(...filtered.map((s) => s.individual_percentage));
      const ranges: number[] = [];
      for (let i = 5; i <= maxPct; i += 10) ranges.push(i);
      ranges.push(maxPct);

      const presentCounts = ranges.map((start, i) => {
        const end = ranges[i + 1] ?? maxPct + 1;
        return filtered.filter(
          (s) =>
            s.individual_percentage >= start && s.individual_percentage < end,
        ).length;
      });

      const mergedCounts = [...presentCounts];
      const mergedRanges = [...ranges];
      for (let i = mergedCounts.length - 1; i > 0; i--) {
        while (mergedCounts[i] < 3 && i > 0) {
          mergedCounts[i - 1] += mergedCounts[i];
          mergedCounts.splice(i, 1);
          mergedRanges.splice(i, 1);
          i--;
        }
      }
      mergedCounts[mergedCounts.length - 1] = filtered.filter(
        (s) => s.individual_percentage >= mergedRanges[mergedRanges.length - 1],
      ).length;

      const presentLabelsRaw = mergedRanges
        .slice(0, mergedCounts.length)
        .map((start, i) => `${start}% – ${mergedRanges[i + 1] ?? maxPct}%`);
      const nonEmpty = mergedCounts
        .map((c, i) =>
          c > 0 ? { label: presentLabelsRaw[i], count: c } : null,
        )
        .filter((x): x is { label: string; count: number } => x !== null);
      const presentLabels = nonEmpty.map((x) => x.label);
      const presentCountsFiltered = nonEmpty.map((x) => x.count);

      if (showAbsentColumn) {
        labels = [ABSENT_LABEL, ...presentLabels];
        counts = [absentCount, ...presentCountsFiltered];
      } else {
        labels = presentLabels;
        counts = presentCountsFiltered;
      }

      const sortedPairs = labels
        .map((l, idx) => ({ label: l, count: counts[idx] }))
        .sort((a, b) => b.count - a.count);
      labels = sortedPairs.map((p) => p.label);
      counts = sortedPairs.map((p) => p.count);

      avg =
        filtered.reduce((acc, s) => acc + s.individual_percentage, 0) /
        totalPresent;
      const sorted = [...filtered].sort(
        (a, b) => a.individual_percentage - b.individual_percentage,
      );
      const mid = Math.floor(totalPresent / 2);
      median =
        totalPresent % 2
          ? sorted[mid].individual_percentage
          : Math.round(
              (sorted[mid - 1].individual_percentage +
                sorted[mid].individual_percentage) /
                2,
            );
    }

    const maxBin = counts.length ? Math.max(...counts) : 0;
    const niceStep =
      maxBin <= 10 ? 2 : maxBin <= 20 ? 5 : maxBin <= 50 ? 10 : 25;

    const absentColor = "rgba(234, 88, 12, 0.55)";
    const absentBorder = "#ea580c";
    const presentColor = "rgba(37, 99, 235, 0.45)";
    const presentBorder = "#2563eb";

    const isAbsentLabel = (l: string) => l === "Отсутствовали";
    const barData = {
      labels,
      datasets: [
        {
          label: "Количество",
          data: counts,
          backgroundColor: labels.map((l) =>
            isAbsentLabel(l) ? absentColor : presentColor,
          ),
          borderColor: labels.map((l) =>
            isAbsentLabel(l) ? absentBorder : presentBorder,
          ),
          borderWidth: 2,
          borderRadius: 8,
          hoverBorderWidth: 0,
          hoverBackgroundColor: labels.map((l) =>
            isAbsentLabel(l) ? absentColor : presentColor,
          ),
          hoverBorderColor: labels.map((l) =>
            isAbsentLabel(l) ? absentBorder : presentBorder,
          ),
          barPercentage: 0.78,
          categoryPercentage: 0.82,
        },
      ],
    };

    return {
      labels,
      counts,
      maxPct,
      totalPeople: totalPresent,
      totalWithAbsent,
      avg,
      median,
      niceStep,
      barData,
    };
  }, [stats]);

  useEffect(() => {
    const maxIndex = (chartData?.labels.length ?? 0) - 1;
    if (selectedLegendIndex !== null && selectedLegendIndex > maxIndex) {
      setSelectedLegendIndex(null);
    }
    if (hoveredLegendIndex !== null && hoveredLegendIndex > maxIndex) {
      setHoveredLegendIndex(null);
    }
  }, [chartData?.labels.length, hoveredLegendIndex, selectedLegendIndex]);

  const formatBucketTooltip = useCallback(
    (value: number, total: number): string => {
      const share = total ? Math.round((value / total) * 100) : 0;
      return `Количество: ${value} (${share}%)`;
    },
    [],
  );

  const chartOptions = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400, easing: "easeOutQuart" as const },
      interaction: {
        mode: "index" as const,
        axis: "x" as const,
        intersect: false,
      },
      hover: { mode: "index" as const, axis: "x" as const, intersect: false },
      onHover: (event: ChartEvent, activeElements: ActiveElement[]) => {
        const target = event.native?.target;
        if (target instanceof HTMLCanvasElement) {
          target.style.cursor =
            activeElements.length > 0 ? "pointer" : "default";
        }
      },
      onClick: (
        _event: ChartEvent,
        activeElements: ActiveElement[],
        chart: Chart,
      ) => {
        if (activeElements.length === 0) {
          setHoveredLegendIndex(null);
          setSelectedLegendIndex(null);
          syncChartActiveState(chart as DashboardChartInstance, null);
          return;
        }

        const clickedIndex = activeElements[0].index;
        setHoveredLegendIndex(null);
        setSelectedLegendIndex((prev) => {
          const next = prev === clickedIndex ? null : clickedIndex;
          syncChartActiveState(chart as DashboardChartInstance, next);
          return next;
        });
      },
      layout: { padding: { right: 8, left: 4, top: 24, bottom: 0 } },
      scales: {
        y: {
          beginAtZero: true,
          suggestedMax: chartData
            ? Math.ceil(
                (Math.max(1, ...chartData.counts) + chartData.niceStep) /
                  chartData.niceStep,
              ) * chartData.niceStep
            : undefined,
          ticks: {
            stepSize: chartData?.niceStep,
            precision: 0,
            color: "#6B7280",
            font: { size: 16, weight: "bold" as const },
            padding: 8,
          },
          grid: {
            color: "rgba(107, 114, 128, 0.18)",
            drawTicks: false,
          },
          title: {
            display: true,
            text: "Количество сотрудников",
            color: "#6B7280",
            font: { size: 16, weight: "bold" as const },
          },
        },
        x: {
          offset: true,
          ticks: {
            autoSkip: true,
            maxTicksLimit: 8,
            maxRotation: 0,
            minRotation: 0,
            padding: 8,
            color: "#6B7280",
            font: { size: 16, weight: "bold" as const },
          },
          grid: {
            color: "rgba(107, 114, 128, 0.12)",
            drawOnChartArea: false,
            drawTicks: false,
          },
          title: {
            display: true,
            text: "Процент времени на работе",
            color: "#6B7280",
            font: { size: 16, weight: "bold" as const },
          },
        },
      },
      plugins: {
        legend: { display: false },
        barDataLabels: { color: undefined },
        tooltip: {
          enabled: false,
        },
      },
    }),
    [chartData, syncChartActiveState],
  );

  const doughnutChartData = useMemo<
    ChartData<"doughnut", number[], string>
  >(() => {
    const lbls = chartData?.labels ?? [];
    const cnts = chartData?.counts ?? [];
    const absentColor = "rgba(234, 88, 12, 0.85)";
    const isAbsent = (l: string) => l === "Отсутствовали";
    let idx = 0;
    const bg = lbls.map((l) => {
      if (isAbsent(l)) return absentColor;
      const hue = 210 + idx * 25;
      idx += 1;
      return `hsl(${hue}, 65%, 52%)`;
    });
    return {
      labels: lbls,
      datasets: [
        {
          data: cnts,
          backgroundColor: bg,
          hoverBackgroundColor: bg,
          hoverBorderWidth: 0,
        },
      ],
    };
  }, [chartData]);

  const doughnutOptions = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 420, easing: "easeOutQuart" as const },
      interaction: { mode: "nearest" as const, intersect: true },
      hover: { mode: "nearest" as const, intersect: true },
      onHover: (event: ChartEvent, activeElements: ActiveElement[]) => {
        const target = event.native?.target;
        if (target instanceof HTMLCanvasElement) {
          target.style.cursor =
            activeElements.length > 0 ? "pointer" : "default";
        }
      },
      onClick: (
        _event: ChartEvent,
        activeElements: ActiveElement[],
        chart: Chart,
      ) => {
        if (activeElements.length === 0) {
          setHoveredLegendIndex(null);
          setSelectedLegendIndex(null);
          syncChartActiveState(chart as DashboardChartInstance, null);
          return;
        }

        const clickedIndex = activeElements[0].index;
        setHoveredLegendIndex(null);
        setSelectedLegendIndex((prev) => {
          const next = prev === clickedIndex ? null : clickedIndex;
          syncChartActiveState(chart as DashboardChartInstance, next);
          return next;
        });
      },
      layout: { padding: { top: 8, right: 8, bottom: 28, left: 8 } },
      plugins: {
        legend: {
          display: true,
          position: "bottom" as const,
          labels: {
            color: "#6B7280",
            font: { size: 12, weight: 600 as const },
            boxWidth: 14,
            boxHeight: 14,
            padding: 12,
          },
        },
        tooltip: {
          enabled: true,
          backgroundColor: "rgba(0, 0, 0, 0.88)",
          padding: 12,
          cornerRadius: 6,
          titleFont: { size: 14, weight: "bold" as const },
          bodyFont: { size: 13, weight: "bold" as const },
          callbacks: {
            title: (items: TooltipItem<"doughnut">[]) => items[0]?.label ?? "",
            label: (ctx: TooltipItem<"doughnut">) => {
              const value = Number(ctx.raw ?? 0);
              const total = chartData?.totalWithAbsent ?? 0;
              return formatBucketTooltip(value, total);
            },
          },
        },
      },
    }),
    [chartData?.totalWithAbsent, formatBucketTooltip, syncChartActiveState],
  );

  const renderDatePicker = () => (
    <div className="flex flex-col items-center gap-1 mb-6">
      <div className="flex items-center gap-2 text-gray-400">
        <span>Дата:</span>
        <EditableDateField
          value={selectedDate}
          onChange={(e) => {
            setSelectedDate(e.target.value);
            setDateMismatchFromBackend(null);
          }}
          containerClassName="inline-block"
          inputClassName="bg-transparent border-b border-gray-400 text-center focus:outline-none transition-all duration-200 text-text-dark dark:text-text-light"
          displayClassName="cursor-pointer hover:underline transition-all duration-200 text-text-dark dark:text-text-light"
        />
      </div>
      {dateMismatchFromBackend && (
        <p
          className="text-xs text-amber-600 dark:text-amber-400 max-w-md text-center"
          role="status"
        >
          {dateMismatchFromBackend}
        </p>
      )}
    </div>
  );

  if (loading) return <LoaderComponent />;
  if (error) {
    return (
      <div className="container mx-auto p-4 max-w-screen-2xl dark:text-gray-100 min-h-screen flex flex-col items-center">
        {renderDatePicker()}
        <div className="flex-1 flex items-start justify-center">
          <Notification message={error} type="error" />
        </div>
      </div>
    );
  }
  if (!stats) {
    return (
      <div className="container mx-auto p-4 max-w-screen-2xl dark:text-gray-100 min-h-screen flex flex-col items-center">
        {renderDatePicker()}
        <div className="flex-1 flex items-start justify-center">
          <Notification message="Данные не были найдены." type="warning" />
        </div>
      </div>
    );
  }
  const absentStaffCount =
    stats.absent_staff_count ?? stats.absent_data?.length ?? 0;
  if (
    (!stats.present_data || stats.present_data.length === 0) &&
    absentStaffCount === 0
  ) {
    const formattedDate = formatDate(stats.data_for_date || selectedDate);
    return (
      <div className="container mx-auto p-4 max-w-screen-2xl dark:text-gray-100 min-h-screen flex flex-col items-center">
        {renderDatePicker()}
        <div className="flex-1 flex items-start justify-center">
          <Notification
            message={`Данные за ${formattedDate} не были найдены, обратитесь к системному администратору.`}
            type="warning"
          />
        </div>
      </div>
    );
  }

  const containerVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { staggerChildren: 0.15, duration: 0.5 },
    },
  };
  const cardVariants = {
    hidden: { opacity: 0, scale: 0.95 },
    visible: { opacity: 1, scale: 1, transition: { duration: 0.3 } },
  };
  const layoutTransition = {
    duration: 0.5,
    ease: [0.22, 1, 0.36, 1] as [number, number, number, number],
  };

  const isKioskOrFullscreen = isKiosk || isFullscreen;
  const isLandscape = width >= height;
  const showSideLegend = isKioskOrFullscreen && isLandscape && width >= 1200;
  const chartHeightClass = isKioskOrFullscreen
    ? "flex-1 min-h-[340px]"
    : "h-72 sm:h-80 md:h-96 lg:h-[28rem] xl:h-[32rem]";
  const chartLayoutKey = `${isKioskOrFullscreen ? "kiosk" : "normal"}-${
    showSideLegend ? "side" : "stack"
  }-${width < 768 ? "mobile" : "desktop"}`;

  const renderLegendPanel = (isSidePanel: boolean) => {
    if (!chartData || chartData.labels.length === 0) return null;

    return (
      <motion.div
        layout
        transition={layoutTransition}
        className={`${isSidePanel ? "min-h-0 h-full" : "mt-3 sm:mt-4 lg:mt-5"}`}
        initial="hidden"
        animate="visible"
        variants={containerVariants}
      >
        <div
          className={`rounded-xl border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 shadow-lg ${
            isSidePanel ? "h-full min-h-0 flex flex-col" : "overflow-hidden"
          }`}
        >
          <div className="px-3 sm:px-4 py-2.5 sm:py-3 border-b border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700/50">
            <h3 className="text-xs sm:text-sm font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-300">
              Легенда графика
            </h3>
            <p className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              Наведение или нажатие подсвечивает столбец и показывает tooltip
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px]">
              <span className="inline-flex items-center rounded-full px-2 py-0.5 bg-blue-100 text-blue-700 dark:bg-blue-900/35 dark:text-blue-200">
                Всего по графику:{" "}
                <b className="ml-1">{chartData.totalWithAbsent}</b>
              </span>
              <span className="inline-flex items-center rounded-full px-2 py-0.5 bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200">
                100%
              </span>
            </div>
          </div>
          <div
            className={`${
              isSidePanel
                ? "min-h-0 flex-1 overflow-visible"
                : "overflow-x-auto overflow-y-visible"
            }`}
          >
            <table className="w-full min-w-[240px] text-xs sm:text-sm table-fixed">
              <thead className="bg-white dark:bg-gray-800">
                <tr className="border-b border-gray-200 dark:border-gray-600">
                  <th className="text-left py-2 sm:py-3 px-2 sm:px-4 font-semibold text-gray-700 dark:text-gray-300 w-8">
                    №
                  </th>
                  <th className="text-left py-2 sm:py-3 px-2 sm:px-4 font-semibold text-gray-700 dark:text-gray-300">
                    Категория
                  </th>
                  <th className="text-right py-2 sm:py-3 px-2 sm:px-4 font-semibold text-gray-700 dark:text-gray-300 tabular-nums">
                    Человек
                  </th>
                  <th className="text-right py-2 sm:py-3 px-2 sm:px-4 font-semibold text-gray-700 dark:text-gray-300 tabular-nums w-16 sm:w-24">
                    % от отдела
                  </th>
                </tr>
              </thead>
              <tbody>
                {chartData.labels.map((label, i) => {
                  const isAbsent = label === "Отсутствовали";
                  const barColor = isAbsent ? "#ea580c" : "#2563eb";
                  const count = chartData.counts[i];
                  const pct =
                    chartData.totalWithAbsent > 0
                      ? Math.round((count / chartData.totalWithAbsent) * 100)
                      : 0;
                  const isActive = activeLegendIndex === i;
                  return (
                    <tr
                      key={`${label}-${i}`}
                      role="button"
                      tabIndex={0}
                      className={`border-b border-gray-100 dark:border-gray-700/70 transition-all duration-200 ease-out cursor-pointer touch-manipulation select-none ${
                        isActive
                          ? "bg-blue-100 dark:bg-blue-900/30 ring-2 ring-inset ring-blue-500/50"
                          : "hover:bg-gray-50 dark:hover:bg-gray-700/30"
                      }`}
                      onClick={() => handleLegendToggle(i)}
                      onMouseEnter={() => handleLegendHover(i)}
                      onMouseLeave={handleLegendLeave}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          handleLegendToggle(i);
                        }
                      }}
                      aria-pressed={isActive}
                      aria-label={`${label}, ${count} человек, ${pct} процентов`}
                    >
                      <td className="py-2.5 sm:py-3 px-2 sm:px-4 text-gray-500 dark:text-gray-400 tabular-nums">
                        {i + 1}
                      </td>
                      <td className="py-2.5 sm:py-3 px-2 sm:px-4">
                        <span className="inline-flex items-center gap-1.5 sm:gap-2">
                          <span
                            className="shrink-0 w-3.5 h-3.5 sm:w-4 sm:h-4 rounded border border-gray-300 dark:border-gray-500"
                            style={{ backgroundColor: barColor }}
                            aria-hidden
                          />
                          <span className="font-medium text-gray-800 dark:text-gray-200 break-words">
                            {label}
                          </span>
                        </span>
                      </td>
                      <td className="py-2.5 sm:py-3 px-2 sm:px-4 text-right font-medium text-gray-800 dark:text-gray-200 tabular-nums">
                        {count}
                      </td>
                      <td className="py-2.5 sm:py-3 px-2 sm:px-4 text-right text-gray-600 dark:text-gray-400 tabular-nums">
                        {pct}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </motion.div>
    );
  };

  return (
    <motion.div
      className={`flex flex-col w-full dark:text-gray-100 touch-manipulation transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] ${
        isKioskOrFullscreen
          ? "fixed inset-0 z-50 min-h-[100dvh] overflow-hidden"
          : "min-h-screen"
      }`}
      initial="hidden"
      animate="visible"
      variants={containerVariants}
    >
      <div
        className={`flex-1 flex flex-col min-h-0 w-full ${
          isKioskOrFullscreen
            ? "mx-auto max-w-none px-2 sm:px-3 md:px-4 py-2 sm:py-3"
            : "container mx-auto p-3 sm:p-4 md:p-5 max-w-screen-2xl"
        }`}
      >
        <h1 className="text-xl sm:text-2xl md:text-3xl lg:text-4xl xl:text-5xl font-bold mb-1 text-center text-text-dark dark:text-text-light flex-shrink-0">
          Посещаемость отдела {stats.department_name}
        </h1>

        <div className="mb-3 sm:mb-5 flex flex-col items-center flex-shrink-0">
          {renderDatePicker()}

          {chartData && chartData.labels.length > 0 && (
            <div className="mt-2 flex flex-wrap justify-center gap-2 text-sm md:text-base">
              {chartData.totalPeople > 0 && (
                <>
                  <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-gray-100 text-gray-700 dark:bg-gray-700/50 dark:text-gray-200">
                    Среднее:&nbsp;
                    <b className="text-text-dark dark:text-text-light">
                      {Math.round(chartData.avg)}%
                    </b>
                  </span>
                  <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-gray-100 text-gray-700 dark:bg-gray-700/50 dark:text-gray-200">
                    Медиана:&nbsp;
                    <b className="text-text-dark dark:text-text-light">
                      {Math.round(chartData.median)}%
                    </b>
                  </span>
                </>
              )}
              <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-gray-100 text-gray-700 dark:bg-gray-700/50 dark:text-gray-200">
                Присутствовали:&nbsp;
                <b className="text-text-dark dark:text-text-light">
                  {stats.present_staff_count}
                </b>
              </span>
              <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-gray-100 text-gray-700 dark:bg-gray-700/50 dark:text-gray-200">
                Всего в отделе:&nbsp;
                <b className="text-text-dark dark:text-text-light">
                  {stats.total_staff_count}
                </b>
              </span>
            </div>
          )}
        </div>

        {stats.total_staff_count === 0 ? (
          <p className="text-center text-gray-400">
            Нет данных для отображения
          </p>
        ) : (
          <motion.div
            layout
            transition={layoutTransition}
            className={`bg-white dark:bg-gray-800 shadow-xl rounded-xl transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] ${
              isKioskOrFullscreen
                ? "flex-1 min-h-0 overflow-hidden"
                : "mb-4 sm:mb-6"
            }`}
            variants={cardVariants}
          >
            <div className="flex items-center justify-between gap-2 px-2 sm:px-4 py-2.5 sm:py-3 border-b border-gray-100 dark:border-gray-700/60">
              <div className="flex-1 min-w-0">
                <h2 className="text-base sm:text-lg md:text-xl lg:text-2xl font-semibold text-center text-gray-700 dark:text-gray-300">
                  Процент посещаемости по сотрудникам
                </h2>
              </div>
              <motion.button
                onClick={handleFullscreenToggle}
                disabled={isFullscreenBusy}
                className={`flex-shrink-0 p-2.5 sm:p-3 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-full text-gray-700 dark:text-gray-200 shadow-lg transition-all duration-300 touch-manipulation ${
                  isFullscreenBusy
                    ? "bg-gray-200 dark:bg-gray-600 cursor-not-allowed"
                    : "bg-white dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600"
                }`}
                aria-label={
                  isFullscreen
                    ? "Выйти из полноэкранного режима"
                    : "Перейти в полноэкранный режим"
                }
              >
                {isFullscreen ? (
                  <FaCompress className="w-5 h-5 sm:w-6 sm:h-6" />
                ) : (
                  <FaExpand className="w-5 h-5 sm:w-6 sm:h-6" />
                )}
              </motion.button>
            </div>

            <div
              className={`grid gap-3 sm:gap-4 px-2 sm:px-4 pb-2 sm:pb-4 ${
                showSideLegend
                  ? "grid-cols-[minmax(0,1fr)_minmax(320px,30vw)]"
                  : "grid-cols-1"
              } ${isKioskOrFullscreen ? "h-full min-h-0" : ""}`}
            >
              <motion.div
                layout
                transition={layoutTransition}
                className="min-h-0 flex flex-col"
              >
                <motion.div
                  layout
                  transition={layoutTransition}
                  ref={diagramRef}
                  className={`relative w-full ${chartHeightClass} min-h-[260px]`}
                >
                  {width < 768 && chartData ? (
                    <Doughnut
                      ref={chartDoughnutRef}
                      key={`doughnut-${chartLayoutKey}`}
                      redraw
                      data={doughnutChartData}
                      options={doughnutOptions}
                    />
                  ) : (
                    chartData && (
                      <Bar
                        ref={chartBarRef}
                        key={`bar-${chartLayoutKey}`}
                        redraw
                        data={chartData.barData}
                        options={chartOptions}
                      />
                    )
                  )}
                </motion.div>

                {!isKioskOrFullscreen && (
                  <motion.div
                    layout
                    transition={layoutTransition}
                    className="mt-3 sm:mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4"
                    initial="hidden"
                    animate="visible"
                    variants={containerVariants}
                  >
                    <motion.div
                      variants={cardVariants}
                      className="min-h-[44px] bg-white dark:bg-gray-800 dark:border dark:border-gray-700 shadow-xl dark:shadow-lg rounded-lg text-center transition-transform duration-200 hover:scale-[1.02] active:scale-[0.98] flex flex-col items-center justify-center touch-manipulation p-4 sm:p-5 md:p-6"
                    >
                      <div className="w-full border-t-4 border-blue-600 mb-2" />
                      <h2 className="font-semibold text-blue-600 text-base sm:text-lg md:text-xl">
                        Всего сотрудников
                      </h2>
                      <p className="font-bold mt-1.5 text-2xl sm:text-3xl md:text-4xl">
                        {stats.total_staff_count}
                      </p>
                      <div className="w-full h-px bg-gray-300 dark:bg-gray-600 mt-4" />
                    </motion.div>

                    <motion.div
                      variants={cardVariants}
                      className="min-h-[44px] bg-white dark:bg-gray-800 dark:border dark:border-gray-700 shadow-xl dark:shadow-lg rounded-lg text-center transition-transform duration-200 hover:scale-[1.02] active:scale-[0.98] flex flex-col items-center justify-center touch-manipulation p-4 sm:p-5 md:p-6"
                    >
                      <div className="w-full border-t-4 border-green-600 mb-2" />
                      <h2 className="font-semibold text-green-600 text-base sm:text-lg md:text-xl">
                        Присутствующие
                      </h2>
                      <p className="font-bold mt-1.5 text-2xl sm:text-3xl md:text-4xl">
                        {stats.present_staff_count}
                      </p>
                      <div className="w-full h-px bg-gray-300 dark:bg-gray-600 mt-4" />
                    </motion.div>

                    <motion.div
                      variants={cardVariants}
                      className="min-h-[44px] bg-white dark:bg-gray-800 dark:border dark:border-gray-700 shadow-xl dark:shadow-lg rounded-lg text-center transition-transform duration-200 hover:scale-[1.02] active:scale-[0.98] flex flex-col items-center justify-center touch-manipulation p-4 sm:p-5 md:p-6"
                    >
                      <div className="w-full border-t-4 border-orange-500 mb-2" />
                      <h2 className="font-semibold text-orange-500 text-base sm:text-lg md:text-xl">
                        Отсутствующие
                      </h2>
                      <p className="font-bold mt-1.5 text-2xl sm:text-3xl md:text-4xl">
                        {stats.absent_staff_count}
                      </p>
                      <div className="w-full h-px bg-gray-300 dark:bg-gray-600 mt-4" />
                    </motion.div>
                  </motion.div>
                )}

                {!showSideLegend && renderLegendPanel(false)}
              </motion.div>

              {showSideLegend && renderLegendPanel(true)}
            </div>
          </motion.div>
        )}
      </div>
    </motion.div>
  );
};

export default Dashboard;
