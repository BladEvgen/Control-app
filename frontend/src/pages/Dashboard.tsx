import React, { useEffect, useState } from "react";
import { Line } from "react-chartjs-2";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { Chart as ChartJS, registerables, TooltipItem } from "chart.js";
import { AttendanceStats } from "../schemas/IData";

ChartJS.register(...registerables);

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<AttendanceStats | null>(null);
  const [selectedDate] = useState<string>(
    new Date().toISOString().split("T")[0]
  );

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await axiosInstance.get(
          `${apiUrl}/api/attendance/stats/`,
          {
            params: { date: selectedDate },
          }
        );
        setStats(response.data);
      } catch (error) {
        console.error(error);
      }
    };

    fetchData();
  }, [selectedDate]);

  if (!stats) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div className="loader"></div>
      </div>
    );
  }

  if (
    stats.total_staff_count === 0 &&
    stats.present_staff_count === 0 &&
    stats.absent_staff_count === 0
  ) {
    return null;
  }

  const previousDate = new Date(
    new Date(selectedDate).setDate(new Date(selectedDate).getDate() - 1)
  ).toLocaleDateString();

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
        label: "Количество:",
        data: staffCountsInRanges,
        fill: false,
        borderColor: "#ff6384",
        backgroundColor: "#ff6384",
        tension: 0.2,
        pointBackgroundColor: "#ff6384",
        pointBorderColor: "#fff",
        pointHoverBackgroundColor: "#fff",
        pointHoverBorderColor: "#ff6384",
        pointRadius: 6,
        pointHoverRadius: 8,
      },
    ],
  };

  const lineOptions = {
    scales: {
      y: {
        beginAtZero: true,
      },
      x: {
        ticks: {
          display: true,
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
      <h1 className="text-2xl font-bold mb-2 text-center">
        Посещаемость отдела {stats.department_name}
      </h1>
      <h2 className="text-lg mb-6 text-center text-gray-600">
        Посещаемость сотрудников на {previousDate}
      </h2>
      {stats.total_staff_count === 0 ? (
        <p className="text-center text-gray-500">Нет данных для отображения</p>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
            <div className="p-6 bg-white shadow-lg rounded-lg">
              <h2 className="text-xl font-semibold">Всего сотрудников</h2>
              <p className="text-3xl font-bold text-green-500">
                {stats.total_staff_count}
              </p>
            </div>
            <div className="p-6 bg-white shadow-lg rounded-lg">
              <h2 className="text-xl font-semibold">Присутствующие</h2>
              <p className="text-3xl font-bold text-blue-500">
                {stats.present_staff_count}
              </p>
            </div>
            <div className="p-6 bg-white shadow-lg rounded-lg">
              <h2 className="text-xl font-semibold">Отсутствующие</h2>
              <p className="text-3xl font-bold text-red-500">
                {stats.absent_staff_count}
              </p>
            </div>
          </div>
          <div className="bg-white shadow-lg rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4 text-center">
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
                      className="flex justify-between bg-gray-50 p-4 rounded-lg shadow-md"
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
