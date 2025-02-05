import ExcelJS from "exceljs";
import { StaffData, AttendanceData } from "../schemas/IData";
import { formatDepartmentName } from "./utils";

export const generateAndDownloadExcel = async (
  staffData: StaffData,
  startDate: string,
  endDate: string
) => {
  if (!staffData) return;

  const sanitizedSurname = staffData.surname ? staffData.surname.trim() : "";
  const sanitizedName = staffData.name ? staffData.name.trim() : "";
  const formattedDepartment = staffData.department
    ? formatDepartmentName(staffData.department.trim())
    : "";

  const fio = `${sanitizedSurname} ${sanitizedName}`.trim() || "Сотрудник";
  const dateRange = `${startDate}__${endDate}`;
  const fileName = `${fio}_${dateRange}.xlsx`;

  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet("Отчет");

  const attendanceHeaderFill: ExcelJS.FillPattern = {
    type: "pattern",
    pattern: "solid",
    fgColor: { argb: "0070C0" },
  };
  const legendHeaderFill: ExcelJS.FillPattern = {
    type: "pattern",
    pattern: "solid",
    fgColor: { argb: "D9E1F2" },
  };
  const attendanceHeaderFont: Partial<ExcelJS.Font> = {
    name: "Arial",
    bold: true,
    color: { argb: "FFFFFF" },
    size: 12,
  };
  const legendHeaderFont: Partial<ExcelJS.Font> = {
    name: "Arial",
    bold: true,
    color: { argb: "000000" },
    size: 12,
  };
  const textFont: Partial<ExcelJS.Font> = {
    name: "Arial",
    color: { argb: "000000" },
    size: 10,
  };
  const headerAlignment: Partial<ExcelJS.Alignment> = {
    vertical: "middle",
    horizontal: "center",
  };

  const rowsToAdd = [
    ["ФИО", fio],
    ["Отдел", formattedDepartment],
    [
      "Процент за период",
      staffData.percent_for_period ? `${staffData.percent_for_period}%` : "0%",
    ],
  ];

  rowsToAdd.forEach((rowData) => {
    const row = worksheet.addRow(rowData);
    row.font = textFont;
    row.eachCell((cell) => {
      cell.border = {
        top: { style: "thin" },
        left: { style: "thin" },
        bottom: { style: "thin" },
        right: { style: "thin" },
      };
    });
  });

  worksheet.addRow([]);

  const legendHeader = ["Цвет", "Описание"];
  const legendHeaderRow = worksheet.addRow(legendHeader);
  legendHeaderRow.font = legendHeaderFont;

  const legendColorHeaderCell = legendHeaderRow.getCell(1);
  legendColorHeaderCell.fill = legendHeaderFill;
  legendColorHeaderCell.alignment = headerAlignment;
  legendColorHeaderCell.border = {
    top: { style: "thin" },
    left: { style: "thin" },
    bottom: { style: "thin" },
    right: { style: "thin" },
  };

  const legendDescriptionHeaderCell = legendHeaderRow.getCell(2);
  legendDescriptionHeaderCell.alignment = {
    vertical: "middle",
    horizontal: "left",
  };
  legendDescriptionHeaderCell.border = {
    top: { style: "thin" },
    left: { style: "thin" },
    bottom: { style: "thin" },
    right: { style: "thin" },
  };

  const colorMap: Record<string, string> = {
    "Выходной день": "F59E0B",
    "Работа в выходной": "34D399",
    "Удаленная работа": "38BDF8",
    "Одобрено": "A78BFA",
    "Не одобрено": "FB7185",
  };
  const legendItems = generateLegendItems(staffData.attendance);

  legendItems.forEach((item) => {
    let fillColor = "";
    for (const key in colorMap) {
      if (item.startsWith(key)) {
        fillColor = colorMap[key];
        break;
      }
    }

    const row = worksheet.addRow([fillColor ? "" : "", item]);
    row.font = textFont;

    const colorCell = row.getCell(1);
    const descriptionCell = row.getCell(2);

    if (fillColor) {
      colorCell.fill = {
        type: "pattern",
        pattern: "solid",
        fgColor: { argb: fillColor },
      };
    }
    colorCell.border = {
      top: { style: "thin" },
      left: { style: "thin" },
      bottom: { style: "thin" },
      right: { style: "thin" },
    };
    colorCell.alignment = {
      vertical: "middle",
      horizontal: "center",
    };

    descriptionCell.border = {
      top: { style: "thin" },
      left: { style: "thin" },
      bottom: { style: "thin" },
      right: { style: "thin" },
    };
    descriptionCell.alignment = {
      vertical: "middle",
      horizontal: "left",
      wrapText: true,
    };
  });

  worksheet.getColumn(1).width = 15;
  worksheet.getColumn(2).width = 50;

  worksheet.addRow([]);

  const attendanceHeader = ["Дата", "Посещаемость", "Процент дня"];
  const attendanceHeaderRow = worksheet.addRow(attendanceHeader);
  attendanceHeaderRow.font = attendanceHeaderFont;

  attendanceHeader.forEach((_, index) => {
    const cell = attendanceHeaderRow.getCell(index + 1);
    cell.fill = attendanceHeaderFill;
    cell.font = attendanceHeaderFont;
    cell.alignment = headerAlignment;
    cell.border = {
      top: { style: "thin" },
      left: { style: "thin" },
      bottom: { style: "thin" },
      right: { style: "thin" },
    };
  });

  const dates = Object.keys(staffData.attendance).sort((a, b) => {
    const [dayA, monthA, yearA] = a.split("-").map(Number);
    const [dayB, monthB, yearB] = b.split("-").map(Number);
    const dateA = new Date(yearA, monthA - 1, dayA).getTime();
    const dateB = new Date(yearB, monthB - 1, dayB).getTime();
    return dateA - dateB;
  });

  dates.forEach((dateKey) => {
    const record = staffData.attendance[dateKey];
    const [day, month, year] = dateKey.split("-");
    const formattedDate = `${day}.${month}.${year}`;

    let attendanceInfo = "";
    if (record.first_in && record.last_out) {
      const firstIn = new Date(record.first_in).toLocaleTimeString("ru-RU");
      const lastOut = new Date(record.last_out).toLocaleTimeString("ru-RU");
      attendanceInfo = `${firstIn} - ${lastOut}`;
    } else if (record.is_weekend) {
      attendanceInfo = "Выходной";
    } else if (record.is_remote_work) {
      attendanceInfo = "Удаленная работа";
    } else {
      if (record.is_absent_approved) {
        attendanceInfo = record.absent_reason || "Одобрено (Без причины)";
      } else {
        attendanceInfo = `Не одобрено: ${
          record.absent_reason || "Без причины"
        }`;
      }
    }

    const dayPercent = record.percent_day
      ? `${record.percent_day.toFixed(2)}%`
      : "0%";

    const row = worksheet.addRow([formattedDate, attendanceInfo, dayPercent]);
    row.font = textFont;

    row.eachCell((cell, colNumber) => {
      let fillColor = "";
      if (colNumber === 2) {
        fillColor = getAttendanceColor(record);
      }

      if (fillColor) {
        cell.fill = {
          type: "pattern",
          pattern: "solid",
          fgColor: { argb: fillColor },
        };
      }
      cell.border = {
        top: { style: "thin" },
        left: { style: "thin" },
        bottom: { style: "thin" },
        right: { style: "thin" },
      };
      cell.alignment = {
        vertical: "middle",
        horizontal: "center",
        wrapText: true,
      };
    });
  });

  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], { type: "application/octet-stream" });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  window.URL.revokeObjectURL(url);
};

const getAttendanceColor = (record: AttendanceData): string => {
  if (record.is_weekend) {
    if (record.first_in && record.last_out) {
      return "34D399";
    } else {
      return "F59E0B";
    }
  } else if (record.is_remote_work) {
    return "38BDF8";
  } else if (record.is_absent_approved) {
    return "A78BFA";
  } else if (!record.first_in && !record.last_out) {
    return "FB7185";
  }
  return "";
};

const generateLegendItems = (
  attendance: Record<string, AttendanceData>
): string[] => {
  const legend = new Set<string>();
  Object.values(attendance).forEach((data) => {
    if (data.is_weekend) {
      if (data.first_in && data.last_out) {
        legend.add("Работа в выходной");
      } else {
        legend.add("Выходной день");
      }
    } else if (data.is_remote_work) {
      legend.add("Удаленная работа");
    } else if (data.is_absent_approved) {
      legend.add(`Одобрено: ${data.absent_reason || "Без причины"}`);
    } else if (!data.first_in && !data.last_out) {
      legend.add(`Не одобрено: ${data.absent_reason || "Без причины"}`);
    }
  });
  return Array.from(legend);
};
