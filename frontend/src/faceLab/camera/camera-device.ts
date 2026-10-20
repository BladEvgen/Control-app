import type { Facing } from "./types";
import { CAMERA_PATTERNS } from "./types";
import { camLog } from "./cameraLog";

type CapRange = { max?: number; min?: number; step?: number };

type ExtendedCapabilities = MediaTrackCapabilities & {
  width?: CapRange;
  height?: CapRange;
  frameRate?: CapRange;
  focusMode?: string[];
  exposureMode?: string[];
  whiteBalanceMode?: string[];
  torch?: boolean;
  zoom?: CapRange;
  sharpness?: CapRange;
  exposureCompensation?: CapRange;
  exposureTime?: CapRange;
  iso?: CapRange;
  colorTemperature?: CapRange;
  contrast?: CapRange;
  saturation?: CapRange;
  brightness?: CapRange;
};

type ExtendedConstraintSet = MediaTrackConstraintSet & {
  focusMode?: string;
  exposureMode?: string;
  whiteBalanceMode?: string;
  torch?: boolean;
  zoom?: number;
  exposureCompensation?: number;
  pointsOfInterest?: Array<{ x: number; y: number }>;
};

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

  const ladder = [
    [1920, 1080],
    [1280, 720],
    [640, 480],
  ].map(([w, h]) => ({
    width: { ideal: w },
    height: { ideal: h },
    frameRate: { ideal: 30, max: 30 },
  }));

  if (deviceId) {
    candidates.push(
      ...ladder.map((c) => ({ deviceId: { exact: deviceId }, ...c })),
    );
  }

  if (facing) {
    candidates.push(
      ...ladder.map((c) => ({ facingMode: { ideal: facing }, ...c })),
    );
  }

  candidates.push({});

  return candidates;
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

  camLog.info("Camera capabilities", {
    width: caps.width,
    height: caps.height,
    frameRate: caps.frameRate,
    focusMode: caps.focusMode,
    exposureMode: caps.exposureMode,
    whiteBalanceMode: caps.whiteBalanceMode,
    zoom: caps.zoom,
    sharpness: caps.sharpness,
    exposureCompensation: caps.exposureCompensation,
    exposureTime: caps.exposureTime,
    iso: caps.iso,
    colorTemperature: caps.colorTemperature,
    contrast: caps.contrast,
    saturation: caps.saturation,
    brightness: caps.brightness,
    torch: caps.torch,
  });

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
