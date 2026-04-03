export type Facing = "user" | "environment";
export type Aspect = "3:4" | "1:1" | "9:16" | "4:3" | "16:9";

export type FaceCameraOverlayRef = {
  open: (facing?: Facing) => Promise<void>;
  close: () => void;
  isActive: () => boolean;
  resetSession: () => void;
};

export type Frame = {
  w: number;
  h: number;
  left: number;
  top: number;
};

export const CAMERA_PATTERNS = {
  FRONT: /(front|user|face\s?time|truedepth)/i,
  BACK: /(back|rear|environment|wide)/i,
  AVOID: /(tele|ultra|macro|depth|mono|ir|tof)/i,
} as const;
