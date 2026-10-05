import axiosInstance from "../api";

export type AttendanceExcelHubState = {
  active: number;
  failedDownload: { filename: string; retry: () => Promise<void> } | null;
  holdCounts: Map<string, number>;
};

type HubListener = (state: AttendanceExcelHubState) => void;

const listeners = new Set<HubListener>();
let active = 0;
let failedDownload: AttendanceExcelHubState["failedDownload"] = null;
const holdCounts = new Map<string, number>();

function snapshotHolds(): Map<string, number> {
  return new Map(holdCounts);
}

function emit(): void {
  const state: AttendanceExcelHubState = {
    active,
    holdCounts: snapshotHolds(),
    failedDownload,
  };
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
  listener({ active, holdCounts: snapshotHolds(), failedDownload });
  return () => {
    listeners.delete(listener);
  };
}

export function getAttendanceExcelDownloadActive(): number {
  return active;
}

export function dismissAttendanceExcelError(): void {
  failedDownload = null;
  emit();
}

export function runAttendanceExcelDownload(options: {
  url: string;
  params: Record<string, string>;
  filename: string;
  holdKey?: string;
}): Promise<void> {
  const holdKey = options.holdKey;
  failedDownload = null;
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
    .catch(() => {
      failedDownload = {
        filename: options.filename,
        retry: () => runAttendanceExcelDownload(options),
      };
    })
    .finally(() => {
      endHold(holdKey);
    });
}
