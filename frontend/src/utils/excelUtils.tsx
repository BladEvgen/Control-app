import ExcelJS from "exceljs";
import { StaffData } from "../schemas/IData";
import {
  attendanceDataRowLegendArgb,
  collectStaffAttendanceLegendChips,
  STAFF_ATTENDANCE_LEGEND_TONE_ARGB,
  hasMeaningfulInOut,
  STAFF_ABSENCE_WITHOUT_REASON_ROW_LABEL,
} from "./attendanceDayPresentation";
import { formatDepartmentName, formatTimeRange, formatMinutes } from "./utils";

export const generateAndDownloadExcel = async (
  staffData: StaffData,
  startDate: string,
  endDate: string,
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

  const legendChips = collectStaffAttendanceLegendChips(staffData.attendance);

  legendChips.forEach((chip) => {
    const fillColor = STAFF_ATTENDANCE_LEGEND_TONE_ARGB[chip.tone];
    const row = worksheet.addRow([fillColor ? "" : "", chip.label]);
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

  const attendanceHeader = [
    "Дата",
    "Посещаемость",
    "Всего времени (ч:мин)",
    "Процент дня",
  ];
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

    let attendanceInfo: string;
    const hasInOut = hasMeaningfulInOut(record);
    const reason = (record.absent_reason ?? "").trim();

    if (record.is_remote_work) {
      if (hasInOut && record.first_in && record.last_out) {
        attendanceInfo = `Удаленная работа, явка ${formatTimeRange(record.first_in, record.last_out)} (${formatMinutes(record.total_minutes)})`;
      } else {
        attendanceInfo = "Удаленная работа";
      }
    } else if (reason !== "") {
      attendanceInfo = record.is_absent_approved
        ? reason || "Одобрено (Без причины)"
        : `Не одобрено: ${reason || "Без причины"}`;
    } else if (record.lesson_attendance_day?.lesson_day_status === "rejected_fraud") {
      attendanceInfo =
        record.lesson_attendance_day.summary_ru?.trim() ||
        "Подозрительное фото — день не в сводке.";
    } else if (
      record.lesson_attendance_day?.lesson_day_status === "pending_manual_review"
    ) {
      attendanceInfo =
        record.lesson_attendance_day.summary_ru?.trim() || "Фото на проверке.";
    } else if (record.is_weekend) {
      const fi = record.first_in;
      const lo = record.last_out;
      if (hasInOut && fi && lo) {
        attendanceInfo = `Работа в выходной: ${formatTimeRange(fi, lo)} (${formatMinutes(record.total_minutes)})`;
      } else {
        attendanceInfo = "Выходной день";
      }
    } else if (hasInOut && record.first_in && record.last_out) {
      attendanceInfo = formatTimeRange(record.first_in, record.last_out);
    } else {
      attendanceInfo = STAFF_ABSENCE_WITHOUT_REASON_ROW_LABEL;
    }

    const totalTimeStr =
      record.total_minutes != null ? formatMinutes(record.total_minutes) : "—";
    const dayPercent = record.percent_day
      ? `${record.percent_day.toFixed(2)}%`
      : "0%";

    const row = worksheet.addRow([
      formattedDate,
      attendanceInfo,
      totalTimeStr,
      dayPercent,
    ]);
    row.font = textFont;

    row.eachCell((cell, colNumber) => {
      let fillColor = "";
      if (colNumber === 2) {
        fillColor = attendanceDataRowLegendArgb(record);
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
        horizontal: colNumber === 2 ? "left" : "center",
        wrapText: colNumber === 2,
      };
    });
  });

  worksheet.getColumn(1).width = 12;
  worksheet.getColumn(2).width = 48;
  worksheet.getColumn(3).width = 20;
  worksheet.getColumn(4).width = 14;

  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], { type: "application/octet-stream" });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  window.URL.revokeObjectURL(url);
};
