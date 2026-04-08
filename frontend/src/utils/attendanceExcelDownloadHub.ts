import axiosInstance from "../api";

export type AttendanceExcelHubState = {
  active: number;
  /** Snapshot: how many in-flight downloads were started for each hold key (e.g. department id). */
  holdCounts: Map<string, number>;
};

type HubListener = (state: AttendanceExcelHubState) => void;

const listeners = new Set<HubListener>();
let active = 0;
const holdCounts = new Map<string, number>();

function snapshotHolds(): Map<string, number> {
  return new Map(holdCounts);
}

function emit(): void {
  const state: AttendanceExcelHubState = { active, holdCounts: snapshotHolds() };
  listeners.forEach((l) => l(state));
}

function beginHold(holdKey?: string): void {
  active += 1;
  if (holdKey) {
    holdCounts.set(holdKey, (holdCounts.get(holdKey) ?? 0) + 1);
  }
  emit();
}

function endHold(holdKey?: string): void {
  active = Math.max(0, active - 1);
  if (holdKey) {
    const next = (holdCounts.get(holdKey) ?? 1) - 1;
    if (next <= 0) {
      holdCounts.delete(holdKey);
    } else {
      holdCounts.set(holdKey, next);
    }
  }
  emit();
}

export function subscribeAttendanceExcelDownloads(
  listener: HubListener,
): () => void {
  listeners.add(listener);
  listener({ active, holdCounts: snapshotHolds() });
  return () => {
    listeners.delete(listener);
  };
}

export function getAttendanceExcelDownloadActive(): number {
  return active;
}

export function runAttendanceExcelDownload(options: {
  url: string;
  params: Record<string, string>;
  filename: string;
  /** When set, that entity’s UI can stay disabled until this request finishes (e.g. department id). */
  holdKey?: string;
}): Promise<void> {
  const holdKey = options.holdKey;
  beginHold(holdKey);
  return axiosInstance
    .get(options.url, {
      params: options.params,
      responseType: "blob",
      timeout: 600_000,
    })
    .then((response) => {
      const blob = new Blob([response.data]);
      const fileUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = fileUrl;
      link.setAttribute("download", options.filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(fileUrl);
    })
    .catch((err) => {
      console.error("Attendance Excel download failed:", err);
    })
    .finally(() => {
      endHold(holdKey);
    });
}
