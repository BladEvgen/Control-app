import { isDebug } from "../../../apiConfig";

export const camLog = {
  info: (...args: unknown[]) => {
    if (isDebug) {
      console.log("[faceLab/camera]", ...args);
    }
  },
};
