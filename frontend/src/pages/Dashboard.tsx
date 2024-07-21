import React, { useEffect, useState } from "react";
import { Line } from "react-chartjs-2";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { Chart as ChartJS, registerables, TooltipItem } from "chart.js";
import { AttendanceStats } from "../schemas/IData";

ChartJS.register(...registerables);

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<AttendanceStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate] = useState<string>(
    new Date().toISOString().split("T")[0]
  );

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError(null);

      try {
        const response = await axiosInstance.get(
          `${apiUrl}/api/attendance/stats/`,
          {
            params: { date: selectedDate },
          }
        );
        setStats(response.data);
      } catch (err) {
        console.error(err);
        setError("Ошибка при загрузке данных. Пожалуйста, попробуйте позже.");
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [selectedDate]);

  useEffect(() => {
    if (!loading && !stats && !error) {
      const timeout = setTimeout(() => {
        setError("Данные не были найдены.");
      }, 5000);
      return () => clearTimeout(timeout);
    }
  }, [loading, stats, error]);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div className="loader"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center h-screen bg-red-100">
        <div
          className="bg-white border border-red-400 text-red-700 px-4 py-3 rounded relative"
          role="alert"
        >
          <strong className="font-bold">Ошибка!</strong>
          <span className="block sm:inline">{error}</span>
        </div>
      </div>
    );
  }

  if (
    !stats ||
    (stats.total_staff_count === 0 &&
      stats.present_staff_count === 0 &&
      stats.absent_staff_count === 0)
  ) {
    return null;
  }

  const formatDate = (dateString: string) => {
    const options: Intl.DateTimeFormatOptions = {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    };
    return new Date(dateString).toLocaleDateString("ru-RU", options);
  };

  const formattedDate = formatDate(stats.data_for_date);

  const filteredData = stats.present_data
    .map((staff) => ({
      ...staff,
      individual_percentage: Math.ceil(staff.individual_percentage),
    }))
    .filter(
      (staff) =>
        staff.individual_percentage >= 5 &&
        !["s34043434", "s89058945"].includes(staff.staff_pin)
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

  const lineData = {
    labels: ranges.slice(0, staffCountsInRanges.length).map((range, index) => {
      const nextRange = ranges[index + 1] || maxPercentage;
      return `${range}% - ${nextRange}%`;
    }),
    datasets: [
      {
        label: "Количество сотрудников",
        data: staffCountsInRanges,
        fill: false,
        borderColor: "#3b82f6",
        backgroundColor: "rgba(59, 130, 246, 0.2)",
        tension: 0.1,
        pointBackgroundColor: "#3b82f6",
        pointBorderColor: "#fff",
        pointHoverBackgroundColor: "#f87171",
        pointHoverBorderColor: "#fff",
        pointRadius: 6,
        pointHoverRadius: 8,
        pointStyle: "circle",
      },
    ],
  };

  const lineOptions = {
    scales: {
      y: {
        beginAtZero: true,
        grid: {
          color: "rgba(0, 0, 0, 0.1)",
        },
        title: {
          display: true,
          text: "Количество сотрудников",
          font: {
            size: 14,
            weight: "bold" as const,
          },
        },
      },
      x: {
        ticks: {
          display: true,
        },
        grid: {
          color: "rgba(0, 0, 0, 0.1)",
        },
        title: {
          display: true,
          text: "Процент времени на работе",
          font: {
            size: 14,
            weight: "bold" as const,
          },
        },
      },
    },
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        callbacks: {
          label: function (context: TooltipItem<"line">) {
            return `Количество: ${context.raw}`;
          },
        },
        backgroundColor: "rgba(0,0,0,0.8)",
        titleFont: {
          size: 16,
        },
        bodyFont: {
          size: 14,
        },
        footerFont: {
          size: 12,
        },
        padding: 10,
        cornerRadius: 3,
      },
    },
  };

  return (
    <div className="container mx-auto p-4">
      <h1 className="text-3xl font-bold mb-4 text-center text-gray-700">
        Посещаемость отдела {stats.department_name}
      </h1>
      <h2 className="text-xl mb-6 text-center text-gray-500">
        Посещаемость сотрудников на {formattedDate}
      </h2>
      {stats.total_staff_count === 0 ? (
        <p className="text-center text-gray-500">Нет данных для отображения</p>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
            <div className="p-6 bg-white shadow-lg rounded-lg text-center">
              <h2 className="text-xl font-semibold text-gray-700">
                Всего сотрудников
              </h2>
              <p className="text-4xl font-bold text-green-600 mt-2">
                {stats.total_staff_count}
              </p>
            </div>
            <div className="p-6 bg-white shadow-lg rounded-lg text-center">
              <h2 className="text-xl font-semibold text-gray-700">
                Присутствующие
              </h2>
              <p className="text-4xl font-bold text-blue-600 mt-2">
                {stats.present_staff_count}
              </p>
            </div>
            <div className="p-6 bg-white shadow-lg rounded-lg text-center">
              <h2 className="text-xl font-semibold text-gray-700">
                Отсутствующие
              </h2>
              <p className="text-4xl font-bold text-red-600 mt-2">
                {stats.absent_staff_count}
              </p>
            </div>
          </div>
          <div className="bg-white shadow-lg rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4 text-center text-gray-700">
              Процент посещаемости по сотрудникам
            </h2>
            <Line data={lineData} options={lineOptions} />
            <div className="mt-4 grid grid-cols-2 gap-4">
              {ranges
                .slice(0, staffCountsInRanges.length)
                .map((range, index) => {
                  const nextRange = ranges[index + 1] || maxPercentage;
                  return (
                    <div
                      key={index}
                      className="flex justify-between bg-gray-100 p-4 rounded-lg shadow-md"
                    >
                      <span className="font-semibold text-gray-700">{`${range}% - ${nextRange}%`}</span>
                      <span className="text-gray-900">{`Сотрудников: ${staffCountsInRanges[index]}`}</span>
                    </div>
                  );
                })}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default Dashboard;
