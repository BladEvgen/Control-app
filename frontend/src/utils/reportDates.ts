export type ReportRange = { startDate: string; endDate: string };

export const REPORT_TIME_ZONE = "Asia/Almaty";

const almatyDateFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: REPORT_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

function utcDate(year: number, monthIndex: number, day: number): string {
  const date = new Date(Date.UTC(year, monthIndex, day));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
}

export function localDate(date: Date = new Date()): string {
  const parts = Object.fromEntries(
    almatyDateFormatter
      .formatToParts(date)
      .filter(({ type }) => type !== "literal")
      .map(({ type, value }) => [type, value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function shiftDate(date: string, days: number): string {
  const parsed = parseDate(date);
  if (!parsed) return date;
  parsed.setUTCDate(parsed.getUTCDate() + days);
  return utcDate(
    parsed.getUTCFullYear(),
    parsed.getUTCMonth(),
    parsed.getUTCDate(),
  );
}

export function parseDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return utcDate(year, month - 1, day) === value ? parsed : null;
}

export function inclusiveDays(startDate: string, endDate: string): number {
  const start = parseDate(startDate);
  const end = parseDate(endDate);
  if (!start || !end || start > end) return 0;
  return Math.round((end.getTime() - start.getTime()) / 86_400_000) + 1;
}

export function formatCalendarDate(
  date: string,
  options: Intl.DateTimeFormatOptions,
): string {
  const parsed = parseDate(date);
  return parsed
    ? parsed.toLocaleDateString("ru-RU", { ...options, timeZone: "UTC" })
    : date;
}

export function presetRange(
  preset: "week" | "month",
  now: Date = new Date(),
): ReportRange {
  const today = localDate(now);
  const parsedToday = parseDate(today)!;
  if (preset === "month") {
    const year = parsedToday.getUTCFullYear();
    const month = parsedToday.getUTCMonth();
    return {
      startDate: utcDate(year, month - 1, 1),
      endDate: utcDate(year, month, 0),
    };
  }
  const endDate = shiftDate(today, -1);
  return { startDate: shiftDate(endDate, -6), endDate };
}

export function validRange(value: unknown): value is ReportRange {
  if (
    !value ||
    typeof value !== "object" ||
    !("startDate" in value) ||
    !("endDate" in value)
  )
    return false;
  const { startDate, endDate } = value;
  const validDate = (date: unknown): date is string =>
    typeof date === "string" && parseDate(date) !== null;
  return validDate(startDate) && validDate(endDate) && startDate <= endDate;
}
