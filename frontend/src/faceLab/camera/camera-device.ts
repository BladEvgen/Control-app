import type { Facing } from "./types";
import { CAMERA_PATTERNS } from "./types";

type ExtendedCapabilities = MediaTrackCapabilities & {
  width?: { max?: number; min?: number };
  height?: { max?: number; min?: number };
  frameRate?: { max?: number; min?: number };
  focusMode?: string[];
  exposureMode?: string[];
  whiteBalanceMode?: string[];
  torch?: boolean;
  zoom?: { max?: number; min?: number; step?: number };
};

type ExtendedConstraintSet = MediaTrackConstraintSet & {
  focusMode?: string;
  exposureMode?: string;
  whiteBalanceMode?: string;
  torch?: boolean;
  zoom?: number;
  pointsOfInterest?: Array<{ x: number; y: number }>;
};

const TRACK_MAX_LONG_EDGE = 1920;

export function isAppleSystemBrowserOnMobile(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  const isIOS =
    /iPad|iPhone|iPod/.test(navigator.platform) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1) ||
    /iPad|iPhone|iPod/.test(ua);
  if (!isIOS) return false;
  if (/CriOS|FxiOS|EdgiOS|OPiOS|OPT\//i.test(ua)) return false;
  return true;
}

export function isWebKitCameraConservativeMode(): boolean {
  if (typeof navigator === "undefined") return false;
  if (isAppleSystemBrowserOnMobile()) return true;
  const ua = navigator.userAgent;
  const isDesktopSafari =
    /Safari/i.test(ua) && !/Chrome|Chromium|Edg|OPR|Opera/i.test(ua);
  return isDesktopSafari;
}

export function computeVideoMirror(input: {
  deviceLabel?: string | undefined;
  mirrorIfUnlabeled: boolean;
  streamFacing: Facing;
}): boolean {
  const isFrontStream =
    input.streamFacing === "user" ||
    (input.deviceLabel
      ? isFrontCamera(input.deviceLabel)
      : input.mirrorIfUnlabeled);

  if (!isFrontStream) return false;
  return true;
}

export function isFrontCamera(deviceLabel: string): boolean {
  return (
    CAMERA_PATTERNS.FRONT.test(deviceLabel) &&
    !CAMERA_PATTERNS.AVOID.test(deviceLabel)
  );
}

export async function listVideoDevices(): Promise<MediaDeviceInfo[]> {
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter((d) => d.kind === "videoinput");
}

export function pickPrimaryCamera(
  devices: MediaDeviceInfo[],
  facing: Facing,
): string | null {
  if (!devices.length) return null;

  const pattern =
    facing === "user" ? CAMERA_PATTERNS.FRONT : CAMERA_PATTERNS.BACK;

  const score = (device: MediaDeviceInfo): number => {
    const label = device.label.toLowerCase();
    let n = pattern.test(label) ? 100 : 0;
    if (CAMERA_PATTERNS.AVOID.test(label)) n -= 80;

    if (facing === "user") {
      if (/(front|user|selfie|facetime|truedepth)/i.test(label)) n += 30;
      if (/(back|rear|environment|world)/i.test(label)) n -= 50;
    } else {
      if (/(back|rear|environment|world)/i.test(label)) n += 30;
      if (/(main|wide|standard|camera 0|0,)/i.test(label)) n += 18;
      if (/(ultra|tele|macro|depth|tof|lidar|ir)/i.test(label)) n -= 55;
      if (/(front|user|selfie|facetime|truedepth)/i.test(label)) n -= 50;
    }

    n -= Math.min(label.length, 80) / 80;
    return n;
  };

  const ranked = [...devices].sort((a, b) => score(b) - score(a));
  if (ranked[0] && score(ranked[0]) > 0) return ranked[0].deviceId;

  const looseCameras = devices.find((d) => pattern.test(d.label));
  if (looseCameras) return looseCameras.deviceId;

  return facing === "user"
    ? devices[devices.length - 1].deviceId
    : devices[0].deviceId;
}

export function createHighQualityConstraints(
  deviceId?: string,
  facing?: Facing,
): MediaTrackConstraints[] {
  const candidates: MediaTrackConstraints[] = [];
  const conservative = isWebKitCameraConservativeMode();
  const mainFace = {
    width: { ideal: conservative ? 1280 : 1920 },
    height: { ideal: conservative ? 960 : 1440 },
    aspectRatio: { ideal: 4 / 3 },
    frameRate: { ideal: 30, max: 30 },
  } satisfies MediaTrackConstraints;
  const fallbackFace = {
    width: { ideal: 1280 },
    height: { ideal: 960 },
    aspectRatio: { ideal: 4 / 3 },
    frameRate: { ideal: 30, max: 30 },
  } satisfies MediaTrackConstraints;
  const standardLandscape = {
    width: { ideal: 1920 },
    height: { ideal: 1080 },
    frameRate: { ideal: 30, max: 30 },
  } satisfies MediaTrackConstraints;

  if (deviceId) {
    candidates.push(
      { deviceId: { exact: deviceId }, ...mainFace },
      { deviceId: { exact: deviceId }, ...fallbackFace },
      { deviceId: { exact: deviceId }, ...standardLandscape },
    );
  }

  if (facing) {
    candidates.push(
      { facingMode: { ideal: facing }, ...mainFace },
      { facingMode: { ideal: facing }, ...fallbackFace },
      { facingMode: { ideal: facing }, ...standardLandscape },
    );
  }

  candidates.push({});

  return candidates;
}

export async function applyMaxVideoResolution(
  track: MediaStreamTrack | null,
): Promise<{ width?: number; height?: number } | null> {
  if (!track?.applyConstraints || !track.getCapabilities) return null;
  try {
    const caps = track.getCapabilities() as ExtendedCapabilities;
    const wMax = caps.width?.max;
    const hMax = caps.height?.max;
    if (!wMax || !hMax) return null;
    let tw = wMax;
    let th = hMax;
    const L = Math.max(tw, th);
    if (L > TRACK_MAX_LONG_EDGE) {
      const s = TRACK_MAX_LONG_EDGE / L;
      tw = Math.max(1, Math.round(tw * s));
      th = Math.max(1, Math.round(th * s));
    }
    await track.applyConstraints({
      width: { ideal: tw },
      height: { ideal: th },
      frameRate: { ideal: 30, max: 30 },
    });
    const s = track.getSettings();
    return { width: s.width, height: s.height };
  } catch {
    return null;
  }
}

export async function optimizeCameraTrackForFace(
  track: MediaStreamTrack | null,
): Promise<{ width?: number; height?: number } | null> {
  if (!track?.applyConstraints) return null;

  const caps =
    typeof track.getCapabilities === "function"
      ? (track.getCapabilities() as ExtendedCapabilities)
      : null;
  if (!caps) {
    const s = track.getSettings();
    return { width: s.width, height: s.height };
  }

  const advanced: ExtendedConstraintSet = {};
  if (caps.focusMode?.includes("continuous")) {
    advanced.focusMode = "continuous";
  }
  if (caps.exposureMode?.includes("continuous")) {
    advanced.exposureMode = "continuous";
  }
  if (caps.whiteBalanceMode?.includes("continuous")) {
    advanced.whiteBalanceMode = "continuous";
  }
  if (caps.torch) {
    advanced.torch = false;
  }
  if (caps.zoom?.min != null && caps.zoom?.max != null) {
    const min = Number(caps.zoom.min);
    const max = Number(caps.zoom.max);
    if (Number.isFinite(min) && Number.isFinite(max)) {
      advanced.zoom = Math.min(Math.max(1, min), max);
    }
  }

  if (Object.keys(advanced).length > 0) {
    try {
      await track.applyConstraints({ advanced: [advanced] });
    } catch {
      /* Optional camera controls differ widely by browser/device. */
    }
  }

  const s = track.getSettings();
  return { width: s.width, height: s.height };
}

export async function applyCameraPointOfInterest(
  track: MediaStreamTrack | null,
  point: { x: number; y: number },
): Promise<void> {
  if (!track?.applyConstraints) return;
  try {
    await track.applyConstraints({
      advanced: [
        {
          pointsOfInterest: [
            {
              x: Math.max(0, Math.min(1, point.x)),
              y: Math.max(0, Math.min(1, point.y)),
            },
          ],
        } as ExtendedConstraintSet,
      ],
    });
  } catch {
    /* Optional on browsers that expose tap-to-focus. */
  }
}
