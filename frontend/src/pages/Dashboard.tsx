import React, { useEffect, useState, useCallback, useMemo } from "react";
import { Line, Pie } from "react-chartjs-2";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";

import { Chart as ChartJS, registerables, TooltipItem } from "chart.js";
import { AttendanceStats } from "../schemas/IData";
import Notification from "../components/Notification";
import LoaderComponent from "../components/LoaderComponent";
import { motion } from "framer-motion";
import useWindowSize from "../hooks/useWindowSize";
import EditableDateField from "../components/EditableDateField";

ChartJS.register(...registerables);

const Dashboard: React.FC<{ pin?: string }> = ({ pin }) => {
  const initialDate = (() => {
    const date = new Date();
    date.setDate(date.getDate() - 1);
    return date.toISOString().split("T")[0];
  })();

  const [selectedDate, setSelectedDate] = useState<string>(initialDate);
  const [editingDate, setEditingDate] = useState<boolean>(false);

  const [stats, setStats] = useState<AttendanceStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const { width } = useWindowSize();

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: any = { date: selectedDate };
      if (pin) {
        params.pin = pin;
      }
      const response = await axiosInstance.get(
        `${apiUrl}/api/attendance/stats/`,
        {
          params,
        }
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

    const filteredData = stats.present_data
      .map((staff) => ({
        ...staff,
        individual_percentage: Math.ceil(staff.individual_percentage),
      }))
      .filter(
        (staff) =>
          staff.individual_percentage >= 5 &&
          !["s99999999", "s99999999998"].includes(staff.staff_pin)
      );

    const maxPercentage = Math.max(
      ...filteredData.map((staff) => staff.individual_percentage)
    );
    const ranges: number[] = [];
    for (let i = 5; i <= maxPercentage; i += 10) {
      ranges.push(i);
    }
    ranges.push(maxPercentage);

    let staffCountsInRanges = ranges.map((range, index) => {
      const nextRange = ranges[index + 1] || maxPercentage + 1;
      return filteredData.filter(
        (staff) =>
          staff.individual_percentage >= range &&
          staff.individual_percentage < nextRange
      ).length;
    });

    for (let i = staffCountsInRanges.length - 1; i > 0; i--) {
      while (staffCountsInRanges[i] < 3 && i > 0) {
        staffCountsInRanges[i - 1] += staffCountsInRanges[i];
        staffCountsInRanges.splice(i, 1);
        ranges.splice(i, 1);
      }
    }
    staffCountsInRanges[staffCountsInRanges.length - 1] = filteredData.filter(
      (staff) => staff.individual_percentage >= ranges[ranges.length - 1]
    ).length;

    const lineColor = "#2563EB";
    const hoverColor = "#F59E0B";

    const lineData = {
      labels: ranges
        .slice(0, staffCountsInRanges.length)
        .map((range, index) => {
          const nextRange = ranges[index + 1] || maxPercentage;
          return `${range}% - ${nextRange}%`;
        }),
      datasets: [
        {
          label: "Количество сотрудников",
          data: staffCountsInRanges,
          fill: false,
          borderColor: lineColor,
          backgroundColor: lineColor,
          tension: 0.1,
          pointBackgroundColor: lineColor,
          pointBorderColor: "#fff",
          pointHoverBackgroundColor: hoverColor,
          pointHoverBorderColor: "#fff",
          pointRadius: 6,
          pointHoverRadius: 10,
          pointStyle: "circle",
        },
      ],
    };

    return { lineData, ranges, staffCountsInRanges, maxPercentage };
  }, [stats]);

  const chartOptions = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 800, easing: "easeInOutQuart" as const },
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: "rgba(107, 114, 128, 0.2)" },
          ticks: {
            color: "#6B7280",
            font: { size: 16, weight: "bold" as const },
          },
          title: {
            display: true,
            text: "Количество сотрудников",
            font: { size: 16, weight: "bold" as const, color: "#6B7280" },
          },
        },
        x: {
          ticks: {
            display: true,
            color: "#6B7280",
            font: { size: 16, weight: "bold" as const },
          },
          grid: { color: "rgba(107, 114, 128, 0.2)" },
          title: {
            display: true,
            text: "Процент времени на работе",
            font: { size: 16, weight: "bold" as const, color: "#6B7280" },
          },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (context: TooltipItem<"line">) =>
              `Количество: ${context.raw}`,
          },
          backgroundColor: "rgba(0, 0, 0, 0.8)",
          titleFont: { size: 18, weight: "bold" as const, color: "#fff" },
          bodyFont: { size: 16, weight: "bold" as const, color: "#fff" },
          footerFont: { size: 14, weight: "bold" as const, color: "#fff" },
          padding: 10,
          cornerRadius: 3,
        },
      },
    }),
    []
  );

  const pieData = useMemo(() => {
    if (!chartData) return null;

    const generateColor = (index: number, total: number, lightness = 50) => {
      const hue = Math.floor((360 / total) * index);
      return `hsl(${hue}, 70%, ${lightness}%)`;
    };

    const totalSegments = chartData.ranges.length;
    const backgroundColors = chartData.ranges.map((_, i) =>
      generateColor(i, totalSegments, 50)
    );
    const hoverBackgroundColors = chartData.ranges.map((_, i) =>
      generateColor(i, totalSegments, 40)
    );

    return {
      labels: chartData.lineData.labels,
      datasets: [
        {
          data: chartData.staffCountsInRanges,
          backgroundColor: backgroundColors,
          hoverBackgroundColor: hoverBackgroundColors,
        },
      ],
    };
  }, [chartData]);

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

  const formattedDate = formatDate(stats.data_for_date);

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
      <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold mb-4 text-center text-gray-200">
        Посещаемость отдела {stats.department_name}
      </h1>
      <h2 className="text-xl md:text-2xl mb-6 text-center text-gray-400">
        Посещаемость сотрудников на{" "}
        <EditableDateField
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          containerClassName="inline-block"
          inputClassName="bg-transparent border-b border-gray-400 text-center focus:outline-none transition-all duration-200 text-gray-200"
          displayClassName="cursor-pointer hover:underline transition-all duration-200"
        />
      </h2>
      {stats.total_staff_count === 0 ? (
        <p className="text-center text-gray-400">Нет данных для отображения</p>
      ) : (
        <>
          <motion.div
            className="bg-white dark:bg-gray-800 shadow-xl rounded-lg mb-6"
            variants={cardVariants}
          >
            <h2 className="text-xl md:text-2xl font-semibold mb-4 text-center text-gray-700 dark:text-gray-300">
              Процент посещаемости по сотрудникам
            </h2>
            <div className="relative w-full h-80 md:h-96 lg:h-[32rem]">
              {width < 768 && pieData ? (
                <Pie
                  key="pie"
                  data={pieData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                      legend: {
                        display: true,
                        position: "bottom",
                        labels: {
                          color: "#6B7280",
                          font: { size: 14 },
                        },
                      },
                    },
                  }}
                />
              ) : (
                chartData && (
                  <Line
                    key="line"
                    data={chartData.lineData}
                    options={chartOptions}
                  />
                )
              )}
            </div>
            <motion.div
              className={`flex flex-col md:flex-row gap-6 mx-4 ${
                width < 768 ? "mt-16" : "mt-6"
              } mb-6 justify-center`}
              initial="hidden"
              animate="visible"
              variants={containerVariants}
            >
              <motion.div
                variants={cardVariants}
                className="flex-1 min-w-[300px] p-6 bg-white dark:bg-gray-800 dark:border dark:border-gray-700 shadow-2xl dark:shadow-xl rounded-lg text-center transition-transform duration-200 hover:scale-105 md:hover:scale-110 md:hover:-translate-y-3 flex flex-col items-center"
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
                className="flex-1 min-w-[300px] p-6 bg-white dark:bg-gray-800 dark:border dark:border-gray-700 shadow-2xl dark:shadow-xl rounded-lg text-center transition-transform duration-200 hover:scale-105 md:hover:scale-110 md:hover:-translate-y-3 flex flex-col items-center"
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
                className="flex-1 min-w-[300px] p-6 bg-white dark:bg-gray-800 dark:border dark:border-gray-700 shadow-2xl dark:shadow-xl rounded-lg text-center transition-transform duration-200 hover:scale-105 md:hover:scale-110 md:hover:-translate-y-3 flex flex-col items-center"
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
            {width >= 768 && (
              <motion.div
                className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4 mx-4"
                initial="hidden"
                animate="visible"
                variants={containerVariants}
              >
                {chartData?.ranges
                  .slice(0, chartData.staffCountsInRanges.length)
                  .map((range, index) => {
                    const nextRange =
                      chartData.ranges[index + 1] || chartData.maxPercentage;
                    return (
                      <motion.div
                        key={index}
                        variants={cardVariants}
                        className="flex flex-col md:flex-row justify-between bg-gray-100 dark:bg-gray-700 dark:border dark:border-gray-600 shadow-2xl dark:shadow-xl p-4 rounded-lg transition-all duration-200 hover:shadow-xl"
                      >
                        <span className="font-semibold text-gray-700 dark:text-gray-300">
                          {`${range}% - ${nextRange}%`}
                        </span>
                        <span className="text-gray-900 dark:text-gray-100">
                          {`Сотрудников: ${chartData.staffCountsInRanges[index]}`}
                        </span>
                      </motion.div>
                    );
                  })}
              </motion.div>
            )}
          </motion.div>
        </>
      )}
    </motion.div>
  );
};

export default Dashboard;
