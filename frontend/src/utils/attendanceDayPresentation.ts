import type { AttendanceData } from "../schemas/IData";

export const STAFF_ABSENCE_WITHOUT_REASON_ROW_LABEL =
  "Отсутствует (Не одобрено)";

const LESSON_FRAUD_FALLBACK_RU = "Подозрительное фото — день не в сводке.";
const LESSON_REVIEW_FALLBACK_RU = "Фото на проверке.";

export function hasMeaningfulInOut(data: AttendanceData): boolean {
  const fi = (data.first_in ?? "").trim();
  const lo = (data.last_out ?? "").trim();
  return fi !== "" && lo !== "";
}

export type StaffAttendanceLegendTone =
  | "sky"
  | "violet"
  | "rose"
  | "amber"
  | "emerald"
  | "green"
  | "gray"
  | "red";

export interface StaffAttendanceLegendChip {
  id: string;
  label: string;
  tone: StaffAttendanceLegendTone;
}

export interface StaffAttendanceRowStyle {
  bg: string;
  border: string;
  hoverBg: string;
  text: string;
  borderLeft: string;
}

const ROW_BASE: Omit<StaffAttendanceRowStyle, "text" | "borderLeft"> = {
  bg: "bg-white dark:bg-gray-950",
  border: "border-gray-200 dark:border-gray-800",
  hoverBg: "hover:bg-gray-50/80 dark:hover:bg-gray-900/60",
};

const LEGEND_TONE_CLASSES: Record<StaffAttendanceLegendTone, string> = {
  sky: "bg-sky-400 dark:bg-sky-500",
  violet: "bg-violet-400 dark:bg-violet-500",
  rose: "bg-rose-400 dark:bg-rose-500",
  amber: "bg-amber-400 dark:bg-amber-500",
  emerald: "bg-emerald-400 dark:bg-emerald-500",
  green: "bg-green-400 dark:bg-green-500",
  gray: "bg-gray-400 dark:bg-gray-500",
  red: "bg-red-400 dark:bg-red-500",
};

export function legendToneClass(tone: StaffAttendanceLegendTone): string {
  return LEGEND_TONE_CLASSES[tone];
}

export interface StaffAttendanceDayVisual {
  rowStatusText: string;
  rowStyle: StaffAttendanceRowStyle;
  legend: Pick<StaffAttendanceLegendChip, "id" | "label" | "tone"> | null;
}

export function resolveStaffAttendanceDayVisual(
  data: AttendanceData,
): StaffAttendanceDayVisual {
  const hasInOut = hasMeaningfulInOut(data);
  const lesson = data.lesson_attendance_day;

  const withStyle = (
    rowStyle: StaffAttendanceRowStyle,
    rowStatusText: string,
    legend: StaffAttendanceDayVisual["legend"],
  ): StaffAttendanceDayVisual => ({ rowStyle, rowStatusText, legend });

  if (data.is_remote_work) {
    return withStyle(
      {
        ...ROW_BASE,
        text: "text-sky-800 dark:text-sky-300",
        borderLeft: "border-l-[3px] border-sky-400/70 dark:border-sky-500/55",
      },
      hasInOut
        ? "Дистанционная работа, явка в здании"
        : "Дистанционная работа",
      { id: "remote", label: "Удаленная работа", tone: "sky" },
    );
  }

  const reason = (data.absent_reason ?? "").trim();
  if (reason !== "") {
    const approved = data.is_absent_approved;
    return withStyle(
      {
        ...ROW_BASE,
        text: approved
          ? "text-violet-800 dark:text-violet-300"
          : "text-rose-800 dark:text-rose-300",
        borderLeft: approved
          ? "border-l-[3px] border-violet-400/70 dark:border-violet-500/55"
          : "border-l-[3px] border-rose-500/75 dark:border-rose-500/50",
      },
      "Отсутствует (" + (approved ? "Одобрено" : "Не одобрено") + ")",
      {
        id: approved ? `absent_ok|${reason}` : `absent_no|${reason}`,
        label: approved ? `Одобрено: ${reason}` : `Не одобрено: ${reason}`,
        tone: approved ? "violet" : "rose",
      },
    );
  }

  if (lesson?.lesson_day_status === "rejected_fraud") {
    const label = lesson.summary_ru?.trim() || LESSON_FRAUD_FALLBACK_RU;
    return withStyle(
      {
        ...ROW_BASE,
        text: "text-rose-800 dark:text-rose-300",
        borderLeft: "border-l-[3px] border-rose-500/75 dark:border-rose-500/50",
      },
      label,
      { id: `lesson_fraud|${label}`, label, tone: "rose" },
    );
  }

  if (lesson?.lesson_day_status === "pending_manual_review") {
    const label = lesson.summary_ru?.trim() || LESSON_REVIEW_FALLBACK_RU;
    return withStyle(
      {
        ...ROW_BASE,
        text: "text-amber-900/90 dark:text-amber-300/90",
        borderLeft:
          "border-l-[3px] border-amber-400/80 dark:border-amber-500/50",
      },
      label,
      { id: `lesson_review|${label}`, label, tone: "amber" },
    );
  }

  if (data.is_weekend) {
    if (hasInOut) {
      return withStyle(
        {
          ...ROW_BASE,
          text: "text-emerald-800 dark:text-emerald-300",
          borderLeft:
            "border-l-[3px] border-emerald-500/65 dark:border-emerald-500/45",
        },
        "Работа в выходной",
        { id: "weekend_work", label: "Работа в выходной", tone: "green" },
      );
    }
    return withStyle(
      {
        ...ROW_BASE,
        text: "text-amber-900/90 dark:text-amber-300/90",
        borderLeft:
          "border-l-[3px] border-amber-400/80 dark:border-amber-500/50",
      },
      "Выходной день",
      { id: "weekend_off", label: "Выходной день", tone: "amber" },
    );
  }

  if (!hasInOut) {
    return withStyle(
      {
        ...ROW_BASE,
        text: "text-rose-800 dark:text-rose-300",
        borderLeft: "border-l-[3px] border-rose-500/75 dark:border-rose-500/50",
      },
      STAFF_ABSENCE_WITHOUT_REASON_ROW_LABEL,
      {
        id: "no_inout",
        label: STAFF_ABSENCE_WITHOUT_REASON_ROW_LABEL,
        tone: "rose",
      },
    );
  }

  return withStyle(
    {
      ...ROW_BASE,
      text: "text-gray-700 dark:text-gray-200",
      borderLeft: "border-l-[3px] border-l-transparent",
    },
    "Рабочий день",
    null,
  );
}

export function collectStaffAttendanceLegendChips(
  attendance: Record<string, AttendanceData>,
): StaffAttendanceLegendChip[] {
  const byId = new Map<string, StaffAttendanceLegendChip>();
  for (const data of Object.values(attendance)) {
    const { legend } = resolveStaffAttendanceDayVisual(data);
    if (!legend) continue;
    if (!byId.has(legend.id)) {
      byId.set(legend.id, {
        id: legend.id,
        label: legend.label,
        tone: legend.tone,
      });
    }
  }
  return Array.from(byId.values());
}

export const STAFF_ATTENDANCE_LEGEND_TONE_ARGB: Record<
  StaffAttendanceLegendTone,
  string
> = {
  sky: "38BDF8",
  violet: "A78BFA",
  rose: "FB7185",
  amber: "F59E0B",
  emerald: "34D399",
  green: "34D399",
  gray: "9CA3AF",
  red: "EF4444",
};

export function attendanceDataRowLegendArgb(data: AttendanceData): string {
  const { legend } = resolveStaffAttendanceDayVisual(data);
  return legend ? STAFF_ATTENDANCE_LEGEND_TONE_ARGB[legend.tone] : "";
}
