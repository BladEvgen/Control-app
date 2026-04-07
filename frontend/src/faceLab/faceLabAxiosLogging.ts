import type { AxiosInstance, InternalAxiosRequestConfig } from "axios";

import { faceLabLog } from "./faceLabLog";

const installed = new WeakMap<AxiosInstance, true>();

function isFaceLabUrl(url: string | undefined): boolean {
  return Boolean(url && url.includes("face-lab"));
}

type TimedConfig = InternalAxiosRequestConfig & { _faceLabT0?: number };

export function installFaceLabAxiosLogging(axios: AxiosInstance): void {
  if (installed.has(axios)) {
    return;
  }
  installed.set(axios, true);

  axios.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    if (!isFaceLabUrl(config.url)) {
      return config;
    }
    (config as TimedConfig)._faceLabT0 = performance.now();
    return config;
  });

  axios.interceptors.response.use(
    (response) => {
      const cfg = response.config as TimedConfig;
      if (!isFaceLabUrl(cfg.url)) {
        return response;
      }
      const t0 = cfg._faceLabT0;
      const ms =
        typeof t0 === "number" ? Math.round(performance.now() - t0) : undefined;
      const fullUrl = cfg.baseURL
        ? `${cfg.baseURL.replace(/\/$/, "")}/${String(cfg.url ?? "").replace(/^\//, "")}`
        : cfg.url;
      faceLabLog.info(
        "HTTP",
        (cfg.method ?? "?").toUpperCase(),
        fullUrl,
        response.status,
        ms != null ? `${ms}ms` : "",
      );
      return response;
    },
    (error) => {
      const cfg = error.config as TimedConfig | undefined;
      if (!cfg || !isFaceLabUrl(cfg.url)) {
        return Promise.reject(error);
      }
      const t0 = cfg._faceLabT0;
      const ms =
        typeof t0 === "number" ? Math.round(performance.now() - t0) : undefined;
      const fullUrl = cfg.baseURL
        ? `${cfg.baseURL.replace(/\/$/, "")}/${String(cfg.url ?? "").replace(/^\//, "")}`
        : cfg.url;
      const data = error.response?.data;
      let errHint = error.message;
      if (
        data &&
        typeof data === "object" &&
        data !== null &&
        "error" in data
      ) {
        errHint = String((data as { error?: unknown }).error).slice(0, 240);
      }
      faceLabLog.warn(
        "HTTP",
        (cfg.method ?? "?").toUpperCase(),
        fullUrl,
        error.response?.status ?? "no-response",
        ms != null ? `${ms}ms` : "",
        errHint,
      );
      return Promise.reject(error);
    },
  );
}
