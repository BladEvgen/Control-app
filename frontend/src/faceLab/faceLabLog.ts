function faceLabLogEnabled(): boolean {
  try {
    if (import.meta.env.DEV) {
      return true;
    }
    return globalThis.localStorage?.getItem("faceLabDebug") === "1";
  } catch {
    return import.meta.env.DEV;
  }
}

export const faceLabLog = {
  isEnabled: faceLabLogEnabled,

  info(...args: unknown[]) {
    if (!faceLabLogEnabled()) {
      return;
    }
    console.info("[faceLab]", ...args);
  },

  warn(...args: unknown[]) {
    if (!faceLabLogEnabled()) {
      return;
    }
    console.warn("[faceLab]", ...args);
  },
};
