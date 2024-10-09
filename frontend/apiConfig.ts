export const isDebug = true;

const localHostname = window.location.hostname;
export const apiUrl = isDebug
  ? `http://${localHostname}:8000`
  : "https://control.krmu.edu.kz";
