const SS_FILE = "faceLabConsentFile";

export function readFileConsent(): boolean {
  try {
    return sessionStorage.getItem(SS_FILE) === "1";
  } catch {
    return false;
  }
}

export function persistFileConsent(): void {
  try {
    sessionStorage.setItem(SS_FILE, "1");
  } catch {
    /* private mode */
  }
}
