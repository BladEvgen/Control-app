const debugFlag = import.meta.env.VITE_APP_DEBUG?.trim().toLowerCase();
export const isDebug =
  debugFlag === "1" || debugFlag === "true" || debugFlag === "yes";

const localHostname = window.location.hostname;
export const apiUrl = isDebug
  ? `http://${localHostname}:8000`
  : "https://control.krmu.edu.kz";
