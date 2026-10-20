import { useCallback, useEffect, useRef, useState } from "react";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import { useAppSelector } from "../store/hooks";
import {
  defaultMapDate,
  parseMapLocations,
  createMapEntries,
  mergeMapEntries,
  type MapEntry,
} from "../components/map/mapModel";
import { localDate, REPORT_TIME_ZONE } from "../utils/reportDates";

const almatyHour = (date = new Date()): number =>
  Number(
    new Intl.DateTimeFormat("en-US", {
      timeZone: REPORT_TIME_ZONE,
      hour: "2-digit",
      hourCycle: "h23",
    }).format(date),
  );

type Snapshot = { date: string; entries: MapEntry[] };

export function useMapLocations() {
  const [date, setDateState] = useState(defaultMapDate);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const dateIsAutomatic = useRef(true);
  const refreshMinutes = useAppSelector(
    (state) => state.ui.reportsAutoRefreshMinutes,
  );

  const refresh = useCallback(
    async (background = false) => {
      if (background && request.current) return;
      request.current?.abort();
      const controller = new AbortController();
      request.current = controller;
      if (!background) setBusy(true);
      setError(null);
      try {
        const response = await axiosInstance.get<unknown>(
          `${apiUrl}/api/locations`,
          {
            params: { employees: true, date_at: date },
            signal: controller.signal,
          },
        );
        const incoming = createMapEntries(parseMapLocations(response.data));
        if (!controller.signal.aborted)
          setSnapshot((current) => {
            const entries = mergeMapEntries(
              current?.date === date ? current.entries : [],
              incoming,
            );
            return current?.date === date && current.entries === entries
              ? current
              : { date, entries };
          });
      } catch {
        if (!controller.signal.aborted)
          setError(
            "Не удалось обновить посещаемость. Проверьте соединение и повторите запрос.",
          );
      } finally {
        if (!controller.signal.aborted) {
          request.current = null;
          setBusy(false);
        }
      }
    },
    [date],
  );

  useEffect(() => {
    void refresh();
    const timer =
      refreshMinutes > 0
        ? window.setInterval(() => void refresh(true), refreshMinutes * 60_000)
        : null;
    return () => {
      request.current?.abort();
      if (timer !== null) window.clearInterval(timer);
    };
  }, [refresh, refreshMinutes]);

  useEffect(() => {
    const updateDefaultDate = (): void => {
      if (
        dateIsAutomatic.current &&
        document.visibilityState === "visible" &&
        almatyHour() >= 8
      )
        setDateState(defaultMapDate());
    };
    const timer = window.setInterval(updateDefaultDate, 60_000);
    document.addEventListener("visibilitychange", updateDefaultDate);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", updateDefaultDate);
    };
  }, []);

  const setDate = (value: string): void => {
    if (!value) return;
    const today = localDate();
    const next = value > today ? today : value;
    dateIsAutomatic.current = next === defaultMapDate();
    setDateState(next);
  };

  const current = snapshot?.date === date ? snapshot : null;
  return {
    date,
    setDate,
    entries: current?.entries ?? [],
    loaded: current !== null,
    busy,
    error,
    refresh,
  };
}
