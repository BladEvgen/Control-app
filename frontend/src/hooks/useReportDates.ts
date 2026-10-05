import { useEffect, useState } from "react";
import {
  localDate,
  presetRange,
  validRange,
  type ReportRange,
} from "../utils/reportDates";

const RANGE_KEY = "control:report-range";

function readRange(): ReportRange {
  try {
    const stored: unknown = JSON.parse(
      sessionStorage.getItem(RANGE_KEY) ?? "null",
    );
    if (validRange(stored) && stored.endDate <= localDate(new Date()))
      return stored;
  } catch {
    /* Storage can be unavailable; the form still works. */
  }
  return presetRange("week");
}

export function useReportDates() {
  const [range, setRange] = useState<ReportRange>(readRange);
  useEffect(() => {
    try {
      sessionStorage.setItem(RANGE_KEY, JSON.stringify(range));
    } catch {
      /* Keep in-memory selection. */
    }
  }, [range]);
  const setStartDate = (startDate: string): void =>
    setRange((current) => ({
      startDate,
      endDate: startDate > current.endDate ? startDate : current.endDate,
    }));
  const setEndDate = (endDate: string): void =>
    setRange((current) => ({
      endDate,
      startDate: endDate < current.startDate ? endDate : current.startDate,
    }));
  return {
    ...range,
    setStartDate,
    setEndDate,
    setRange,
    today: localDate(new Date()),
  };
}
