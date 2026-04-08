export function jwtCookieMaxAgeSeconds(token: string): number {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return 3600;
    const payload = JSON.parse(atob(parts[1])) as { exp?: number };
    if (typeof payload.exp !== "number") return 3600;
    const sec = Math.floor(payload.exp - Date.now() / 1000);
    return Math.max(60, sec);
  } catch {
    return 3600;
  }
}
