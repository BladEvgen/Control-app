export type ReportRange = { startDate: string; endDate: string };

export function localDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function presetRange(
  preset: "week" | "month",
  now: Date = new Date(),
): ReportRange {
  if (preset === "month")
    return {
      startDate: localDate(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
      endDate: localDate(new Date(now.getFullYear(), now.getMonth(), 0)),
    };
  const end = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  const start = new Date(end.getFullYear(), end.getMonth(), end.getDate() - 6);
  return { startDate: localDate(start), endDate: localDate(end) };
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
  const validDate = (date: unknown): date is string => {
    if (typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(date))
      return false;
    const parsed = new Date(`${date}T12:00:00`);
    return Number.isFinite(parsed.getTime()) && localDate(parsed) === date;
  };
  return validDate(startDate) && validDate(endDate) && startDate <= endDate;
}
