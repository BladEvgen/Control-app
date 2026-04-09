import type { Facing } from "./types";
import { CAMERA_PATTERNS } from "./types";

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

  const goodCameras = devices.filter(
    (d) => pattern.test(d.label) && !CAMERA_PATTERNS.AVOID.test(d.label),
  );

  if (goodCameras.length > 0) {
    goodCameras.sort((a, b) => a.label.length - b.label.length);
    return goodCameras[0].deviceId;
  }

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
  const highResLandscape = {
    width: { ideal: 2560 },
    height: { ideal: 1440 },
    frameRate: { ideal: 30, max: 60 },
  } satisfies MediaTrackConstraints;
  const standardLandscape = {
    width: { ideal: 1920 },
    height: { ideal: 1080 },
    frameRate: { ideal: 30, max: 60 },
  } satisfies MediaTrackConstraints;
  const balancedPortraitCrop = {
    width: { ideal: 1440 },
    height: { ideal: 1080 },
    aspectRatio: { ideal: 4 / 3 },
    frameRate: { ideal: 30, max: 60 },
  } satisfies MediaTrackConstraints;

  if (deviceId) {
    if (conservative) {
      candidates.push({
        deviceId: { exact: deviceId },
        frameRate: { ideal: 30, max: 60 },
      });
    } else {
      candidates.push(
        { deviceId: { exact: deviceId }, ...highResLandscape },
        { deviceId: { exact: deviceId }, ...standardLandscape },
        { deviceId: { exact: deviceId }, ...balancedPortraitCrop },
      );
    }
  }

  if (facing) {
    if (conservative) {
      candidates.push({
        facingMode: { ideal: facing },
        frameRate: { ideal: 30, max: 60 },
      });
    } else {
      candidates.push(
        { facingMode: { ideal: facing }, ...highResLandscape },
        { facingMode: { ideal: facing }, ...standardLandscape },
        { facingMode: { ideal: facing }, ...balancedPortraitCrop },
      );
    }
  }

  candidates.push({});

  return candidates;
}

export async function applyMaxVideoResolution(
  track: MediaStreamTrack | null,
): Promise<{ width?: number; height?: number } | null> {
  if (!track?.applyConstraints || !track.getCapabilities) return null;
  if (isWebKitCameraConservativeMode()) {
    const s = track.getSettings();
    return { width: s.width, height: s.height };
  }
  try {
    const caps = track.getCapabilities() as MediaTrackCapabilities & {
      width?: { max?: number; min?: number };
      height?: { max?: number; min?: number };
    };
    const wMax = caps.width?.max;
    const hMax = caps.height?.max;
    if (!wMax || !hMax) return null;
    const TRACK_MAX_LONG = 2560;
    let tw = wMax;
    let th = hMax;
    const L = Math.max(tw, th);
    if (L > TRACK_MAX_LONG) {
      const s = TRACK_MAX_LONG / L;
      tw = Math.max(1, Math.round(tw * s));
      th = Math.max(1, Math.round(th * s));
    }
    await track.applyConstraints({
      width: { ideal: tw },
      height: { ideal: th },
    });
    const s = track.getSettings();
    return { width: s.width, height: s.height };
  } catch {
    return null;
  }
}
