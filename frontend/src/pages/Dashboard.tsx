import React, {
  useEffect,
  useState,
  useCallback,
  useMemo,
  useRef,
} from "react";
import { Bar, Doughnut } from "react-chartjs-2";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import {
  Chart as ChartJS,
  registerables,
  TooltipItem,
  ChartData,
} from "chart.js";
import { AttendanceStats } from "../schemas/IData";
import Notification from "../components/Notification";
import LoaderComponent from "../components/LoaderComponent";
import { motion } from "framer-motion";
import useWindowSize from "../hooks/useWindowSize";
import EditableDateField from "../components/EditableDateField";
import { FaCompress, FaExpand } from "react-icons/fa";

ChartJS.register(...registerables);

const Dashboard: React.FC<{ pin?: string }> = ({ pin }) => {
  const initialDate = (() => {
    const date = new Date();
    date.setDate(date.getDate() - 1);
    return date.toISOString().split("T")[0];
  })();

  const [selectedDate, setSelectedDate] = useState<string>(initialDate);
  const [stats, setStats] = useState<AttendanceStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const { width } = useWindowSize();

  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const diagramRef = useRef<HTMLDivElement>(null);

  const handleFullscreenChange = useCallback(() => {
    const isFs = !!document.fullscreenElement;
    setIsFullscreen(isFs);
  }, []);

  useEffect(() => {
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
    };
  }, [handleFullscreenChange]);

  const handleFullscreenToggle = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch((err) => {
        console.error("Ошибка при входе в полноэкранный режим:", err);
      });
    } else {
      document.exitFullscreen();
    }
  }, []);

  useEffect(() => {
    if (isFullscreen) {
      if (diagramRef.current) {
        const elementTop =
          diagramRef.current.getBoundingClientRect().top + window.scrollY;
        const offset = window.innerHeight * 0.16;
        window.scrollTo({ top: elementTop - offset, behavior: "smooth" });
      }
    } else {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [isFullscreen]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    const todayStr = new Date().toISOString().split("T")[0];
    if (selectedDate > todayStr) {
      setError("Выбранная дата не может быть в будущем");
      setLoading(false);
      return;
    }

    try {
      const params: any = { date: selectedDate };
      if (pin) params.pin = pin;

      const response = await axiosInstance.get(
        `${apiUrl}/api/attendance/stats/`,
        { params }
      );
      setStats(response.data);
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
    if (stats && stats.data_for_date && stats.data_for_date !== selectedDate) {
      setSelectedDate(stats.data_for_date);
    }
  }, [stats, selectedDate]);

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

    const filtered = stats.present_data
      .map((s) => ({
        ...s,
        individual_percentage: Math.ceil(s.individual_percentage),
      }))
      .filter(
        (s) =>
          s.individual_percentage >= 5 &&
          !["s99999999", "s99999999998"].includes(s.staff_pin)
      );

    const totalPeople = filtered.length;

    if (!totalPeople) {
      return {
        labels: [],
        counts: [],
        maxPct: 0,
        avg: 0,
        median: 0,
        niceStep: 1,
        barData: { labels: [], datasets: [] },
      };
    }

    const maxPct = Math.max(...filtered.map((s) => s.individual_percentage));

    const ranges: number[] = [];
    for (let i = 5; i <= maxPct; i += 10) ranges.push(i);
    ranges.push(maxPct);

    let counts = ranges.map((start, i) => {
      const end = ranges[i + 1] || maxPct + 1;
      return filtered.filter(
        (s) => s.individual_percentage >= start && s.individual_percentage < end
      ).length;
    });

    for (let i = counts.length - 1; i > 0; i--) {
      while (counts[i] < 3 && i > 0) {
        counts[i - 1] += counts[i];
        counts.splice(i, 1);
        ranges.splice(i, 1);
      }
    }

    counts[counts.length - 1] = filtered.filter(
      (s) => s.individual_percentage >= ranges[ranges.length - 1]
    ).length;

    const labels = ranges
      .slice(0, counts.length)
      .map((start, i) => `${start}% - ${ranges[i + 1] ?? maxPct}%`);

    const avg =
      filtered.reduce((acc, s) => acc + s.individual_percentage, 0) /
      totalPeople;

    const sorted = [...filtered].sort(
      (a, b) => a.individual_percentage - b.individual_percentage
    );
    const mid = Math.floor(totalPeople / 2);
    const median =
      totalPeople % 2
        ? sorted[mid].individual_percentage
        : Math.round(
            (sorted[mid - 1].individual_percentage +
              sorted[mid].individual_percentage) /
              2
          );

    const maxBin = counts.length ? Math.max(...counts) : 0;
    const niceStep =
      maxBin <= 10 ? 2 : maxBin <= 20 ? 5 : maxBin <= 50 ? 10 : 25;

    const barData = {
      labels,
      datasets: [
        {
          label: "Количество сотрудников",
          data: counts,
          backgroundColor: "rgba(37, 99, 235, 0.35)",
          borderColor: "#2563EB",
          borderWidth: 2,
          borderRadius: 6,
          hoverBackgroundColor: "rgba(245, 158, 11, 0.5)",
          hoverBorderColor: "#F59E0B",
          barPercentage: 0.8,
          categoryPercentage: 0.8,
        },
      ],
    };

    return {
      labels,
      counts,
      maxPct,
      totalPeople,
      avg,
      median,
      niceStep,
      barData,
    };
  }, [stats]);

  const chartOptions = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 800, easing: "easeInOutQuart" as const },
      interaction: { mode: "index" as const, intersect: false },
      layout: { padding: { right: 8, left: 4, top: 0, bottom: 0 } },
      scales: {
        y: {
          beginAtZero: true,
          suggestedMax: chartData
            ? Math.ceil(
                (Math.max(1, ...chartData.counts) + chartData.niceStep) /
                  chartData.niceStep
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
        tooltip: {
          backgroundColor: "rgba(0, 0, 0, 0.85)",
          padding: 10,
          cornerRadius: 4,
          titleFont: { size: 18, weight: "bold" as const },
          bodyFont: { size: 16, weight: "bold" as const },
          callbacks: {
            title: (items: TooltipItem<"bar">[]) => items[0]?.label ?? "",
            label: (ctx: TooltipItem<"bar">) => {
              const value = Number(ctx.raw ?? 0);
              const total = chartData?.totalPeople ?? 0;
              const share = total ? Math.round((value / total) * 100) : 0;
              return `Количество: ${value} (${share}%)`;
            },
          },
        },
      },
    }),
    [chartData]
  );

  const doughnutChartData = useMemo<ChartData<"doughnut", number[], string>>(
    () => ({
      labels: chartData?.labels ?? [],
      datasets: [
        {
          data: chartData?.counts ?? [],
          backgroundColor: (chartData?.labels ?? []).map((_, i) => {
            const hue = Math.floor((360 / (chartData?.labels.length || 1)) * i);
            return `hsl(${hue}, 70%, 50%)`;
          }),
          hoverBackgroundColor: (chartData?.labels ?? []).map((_, i) => {
            const hue = Math.floor((360 / (chartData?.labels.length || 1)) * i);
            return `hsl(${hue}, 70%, 40%)`;
          }),
        },
      ],
    }),
    [chartData]
  );

  if (loading) return <LoaderComponent />;
  if (error) return <Notification message={error} type="error" />;
  if (!stats)
    return <Notification message="Данные не были найдены." type="warning" />;
  if (stats.present_data.length === 0) {
    const formattedDate = formatDate(stats.data_for_date || selectedDate);
    return (
      <Notification
        message={`Данные за ${formattedDate} не были найдены, обратитесь к системному администратору.`}
        type="warning"
      />
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

  return (
    <motion.div
      className="container mx-auto p-4 max-w-screen-2xl dark:text-gray-100"
      initial="hidden"
      animate="visible"
      variants={containerVariants}
    >
      <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold mb-1 text-center text-text-dark dark:text-text-light">
        Посещаемость отдела {stats.department_name}
      </h1>

      <div className="mb-5 flex flex-col items-center">
        <div className="flex items-center gap-2 text-gray-400">
          <span>Дата:</span>
          <EditableDateField
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            containerClassName="inline-block"
            inputClassName="bg-transparent border-b border-gray-400 text-center focus:outline-none transition-all duration-200 text-text-dark dark:text-text-light"
            displayClassName="cursor-pointer hover:underline transition-all duration-200 text-text-dark dark:text-text-light"
          />
        </div>

        {chartData && (
          <div className="mt-2 flex flex-wrap justify-center gap-2 text-sm md:text-base">
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
            <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-gray-100 text-gray-700 dark:bg-gray-700/50 dark:text-gray-200">
              Участников анализа:&nbsp;
              <b className="text-text-dark dark:text-text-light">
                {chartData.totalPeople}
              </b>
            </span>
          </div>
        )}
      </div>

      {stats.total_staff_count === 0 ? (
        <p className="text-center text-gray-400">Нет данных для отображения</p>
      ) : (
        <>
          <motion.div
            className="bg-white dark:bg-gray-800 shadow-xl rounded-lg mb-6"
            variants={cardVariants}
          >
            <h2 className="text-xl md:text-2xl font-semibold mb-1 text-center text-gray-700 dark:text-gray-300">
              Процент посещаемости по сотрудникам
            </h2>

            <div className="flex justify-end pr-4 pb-2 landscape:hidden lg:landscape:flex">
              <motion.button
                onClick={handleFullscreenToggle}
                className="bg-white text-gray-700 p-3 rounded-full shadow-lg hover:bg-gray-100 transition-all duration-200"
                aria-label={
                  isFullscreen
                    ? "Выйти из полноэкранного режима"
                    : "Перейти в полноэкранный режим"
                }
              >
                {isFullscreen ? (
                  <FaCompress className="w-5 h-5 sm:w-6 sm:h-6 md:w-7 md:h-7" />
                ) : (
                  <FaExpand className="w-5 h-5 sm:w-6 sm:h-6 md:w-7 md:h-7" />
                )}
              </motion.button>
            </div>

            <div
              ref={diagramRef}
              className="relative w-full h-96 md:h-96 lg:h-[32rem]"
            >
              {width < 768 && chartData ? (
                <Doughnut
                  key="doughnut"
                  data={doughnutChartData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    layout: { padding: { bottom: 40 } },
                    plugins: {
                      legend: {
                        display: true,
                        position: "bottom",
                        labels: { color: "#6B7280", font: { size: 14 } },
                      },
                      tooltip: {
                        callbacks: {
                          label: (ctx) => {
                            const value = Number(ctx.raw ?? 0);
                            const total = chartData.totalPeople;
                            const share = total
                              ? Math.round((value / total) * 100)
                              : 0;
                            return ` ${value} (${share}%)`;
                          },
                        },
                      },
                    },
                  }}
                />
              ) : (
                chartData && (
                  <Bar
                    key="bar"
                    data={chartData.barData}
                    options={chartOptions}
                  />
                )
              )}
            </div>

            <motion.div
              className={`flex flex-col md:flex-row flex-wrap gap-6 mx-4 ${
                width < 768 ? "mt-16" : "mt-6"
              } mb-6 justify-center`}
              initial="hidden"
              animate="visible"
              variants={containerVariants}
            >
              <motion.div
                variants={cardVariants}
                className="flex-1 min-w-[200px] md:min-w-[300px] p-6 bg-white dark:bg-gray-800 dark:border dark:border-gray-700 shadow-2xl dark:shadow-xl rounded-lg text-center transition-transform duration-200 hover:scale-105 md:hover:scale-110 md:hover:-translate-y-3 flex flex-col items-center"
              >
                <div className="w-full border-t-4 border-blue-600 mb-2"></div>
                <h2 className="text-xl font-semibold text-blue-600">
                  Всего сотрудников
                </h2>
                <p className="text-4xl font-bold mt-2">
                  {stats.total_staff_count}
                </p>
                <div className="w-full h-px bg-gray-300 dark:bg-gray-600 mt-4"></div>
              </motion.div>

              <motion.div
                variants={cardVariants}
                className="flex-1 min-w-[200px] md:min-w-[300px] p-6 bg-white dark:bg-gray-800 dark:border dark:border-gray-700 shadow-2xl dark:shadow-xl rounded-lg text-center transition-transform duration-200 hover:scale-105 md:hover:scale-110 md:hover:-translate-y-3 flex flex-col items-center"
              >
                <div className="w-full border-t-4 border-green-600 mb-2"></div>
                <h2 className="text-xl font-semibold text-green-600">
                  Присутствующие
                </h2>
                <p className="text-4xl font-bold mt-2">
                  {stats.present_staff_count}
                </p>
                <div className="w-full h-px bg-gray-300 dark:bg-gray-600 mt-4"></div>
              </motion.div>

              <motion.div
                variants={cardVariants}
                className="flex-1 min-w-[200px] md:min-w-[300px] p-6 bg-white dark:bg-gray-800 dark:border dark:border-gray-700 shadow-2xl dark:shadow-xl rounded-lg text-center transition-transform duration-200 hover:scale-105 md:hover:scale-110 md:hover:-translate-y-3 flex flex-col items-center"
              >
                <div className="w-full border-t-4 border-orange-500 mb-2"></div>
                <h2 className="text-xl font-semibold text-orange-500">
                  Отсутствующие
                </h2>
                <p className="text-4xl font-bold mt-2">
                  {stats.absent_staff_count}
                </p>
                <div className="w-full h-px bg-gray-300 dark:bg-gray-600 mt-4"></div>
              </motion.div>
            </motion.div>

            {width >= 768 && chartData && (
              <motion.div
                className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4 mx-4"
                initial="hidden"
                animate="visible"
                variants={containerVariants}
              >
                {chartData.labels.map((label, i) => (
                  <motion.div
                    key={label}
                    variants={cardVariants}
                    className="flex flex-col md:flex-row justify-between bg-gray-100 dark:bg-gray-700 dark:border dark:border-gray-600 shadow-2xl dark:shadow-xl p-4 rounded-lg transition-all duration-200 hover:shadow-xl"
                  >
                    <span className="font-semibold text-gray-700 dark:text-gray-300">
                      {label}
                    </span>
                    <span className="text-gray-900 dark:text-gray-100">
                      {`Сотрудников: ${chartData.counts[i]}`}
                    </span>
                  </motion.div>
                ))}
              </motion.div>
            )}
          </motion.div>
        </>
      )}
    </motion.div>
  );
};

export default Dashboard;
