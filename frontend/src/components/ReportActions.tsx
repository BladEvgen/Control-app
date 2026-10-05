import { useEffect, useState } from "react";
import { FaChevronDown, FaDownload, FaRegCalendarAlt } from "react-icons/fa";
import DateInput from "./DateInput";
import Dropdown from "./Dropdown";
import { subscribeAttendanceExcelDownloads } from "../utils/attendanceExcelDownloadHub";

type ReportActionsProps = {
  startDate: string;
  endDate: string;
  setStartDate: (date: string) => void;
  setEndDate: (date: string) => void;
  today: string;
  onDownload: () => void;
  holdKey: string;
};

const shortDate = (date: string): string =>
  new Date(`${date}T12:00:00`).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
  });

export default function ReportActions({
  startDate,
  endDate,
  setStartDate,
  setEndDate,
  today,
  onDownload,
  holdKey,
}: ReportActionsProps) {
  const [holdCounts, setHoldCounts] = useState<Map<string, number>>(new Map());
  useEffect(
    () =>
      subscribeAttendanceExcelDownloads(({ holdCounts: next }) =>
        setHoldCounts(next),
      ),
    [],
  );
  const busy = (holdCounts.get(holdKey) ?? 0) > 0;

  return (
    <div className="detail-actions">
      <Dropdown
        align="end"
        panelClassName="ws-period-panel"
        trigger={({ toggle, ...aria }) => (
          <button type="button" className="ws-chip" onClick={toggle} {...aria}>
            <FaRegCalendarAlt aria-hidden />
            {startDate === endDate
              ? shortDate(startDate)
              : `${shortDate(startDate)} — ${shortDate(endDate)}`}
            <FaChevronDown className="ws-chevron" aria-hidden />
          </button>
        )}
      >
        <div className="ws-period-fields">
          <DateInput
            label="С"
            id="report-start"
            value={startDate}
            max={today}
            onChange={(event) =>
              event.target.value && setStartDate(event.target.value)
            }
          />
          <DateInput
            label="По"
            id="report-end"
            value={endDate}
            max={today}
            onChange={(event) =>
              event.target.value && setEndDate(event.target.value)
            }
          />
        </div>
      </Dropdown>
      <button
        type="button"
        className="ws-btn-primary"
        onClick={onDownload}
        disabled={busy}
        aria-busy={busy}
      >
        {busy ? (
          <span className="ws-spinner" aria-hidden />
        ) : (
          <FaDownload aria-hidden />
        )}
        Скачать Excel
      </button>
    </div>
  );
}
