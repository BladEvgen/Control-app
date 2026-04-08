import { useEffect } from "react";
import { installAuthWakeRefreshListeners } from "./wakeListeners.ts";

export function AuthSessionWakeBridge(): null {
  useEffect(() => {
    return installAuthWakeRefreshListeners();
  }, []);

  return null;
}
