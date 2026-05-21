const SKIP_PAGE_MOTION_STORAGE_KEY = "__skip_page_motion__";

const isBrowser = typeof window !== "undefined";

export const markSkipPageMotionOnNextBoot = (): void => {
  if (!isBrowser) return;
  try {
    sessionStorage.setItem(SKIP_PAGE_MOTION_STORAGE_KEY, "1");
  } catch {
    // ignore storage issues
  }
};

export const shouldSkipPageMotion = (): boolean => {
  if (!isBrowser) return false;
  try {
    return sessionStorage.getItem(SKIP_PAGE_MOTION_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
};

export const consumeSkipPageMotion = (): boolean => {
  if (!shouldSkipPageMotion()) return false;
  try {
    sessionStorage.removeItem(SKIP_PAGE_MOTION_STORAGE_KEY);
  } catch {
    // ignore storage issues
  }
  return true;
};

export const pageMotionInitial = (skip: boolean): false | undefined =>
  skip ? false : undefined;
