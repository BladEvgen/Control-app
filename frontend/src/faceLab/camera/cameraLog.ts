import { faceLabLog } from "../faceLabLog";

export const camLog = {
  info: (...args: unknown[]) => {
    faceLabLog.info("camera", ...args);
  },
};
