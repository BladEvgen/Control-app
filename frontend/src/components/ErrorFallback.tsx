import { useRouteError } from "react-router-dom";
import { useEffect, useMemo } from "react";
import {
  FaExclamationTriangle,
  FaHome,
  FaRedo,
  FaCircle,
} from "react-icons/fa";
import {
  forceHardReload,
  isChunkLoadError,
  tryRecoverChunkLoadError,
} from "../utils/chunkRecovery";

const FRIENDLY_HINTS = [
  "Проверьте подключение к интернету",
  "Сервер может быть временно перезагружен",
  "Попробуйте обновить страницу или зайти позже",
];

function getBrowserMismatchInfo(
  error: unknown,
): { reason: string; solution: string } | null {
  const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
  const errMsg = error instanceof Error ? error.message : String(error);
  const isTvBrowser = /TV|SmartTV|Tizen|WebOS|NetCast|HbbTV|Viera|BRAVIA/i.test(
    ua,
  );
  const chromeVersionMatch = ua.match(/Chrome\/(\d+)/i);
  const chromeMajor = chromeVersionMatch ? Number(chromeVersionMatch[1]) : null;

  if (/\bMSIE\b|Trident\//i.test(ua)) {
    return {
      reason: "Internet Explorer не поддерживается.",
      solution: "Используйте актуальный браузер.",
    };
  }
  if (isTvBrowser) {
    return {
      reason:
        "Встроенный браузер телевизора часто не поддерживает современные веб-приложения.",
      solution:
        "Обновите браузер/ПО телевизора. Если не помогло, откройте дашборд на ПК или телефоне.",
    };
  }
  if (chromeMajor !== null && chromeMajor < 90) {
    return {
      reason: `Слишком старая версия браузера (Chromium ${chromeMajor}).`,
      solution:
        "Обновите браузер до более новой версии или используйте современный браузер на другом устройстве.",
    };
  }
  if (
    /SyntaxError|Unexpected token|is not a function|undefined is not/i.test(
      errMsg,
    )
  ) {
    return {
      reason: "Браузер не поддерживает приложение.",
      solution: "Обновите браузер или откройте на другом устройстве.",
    };
  }
  return null;
}

const ErrorFallback: React.FC = () => {
  const error = useRouteError();
  const browserMismatch = useMemo(() => getBrowserMismatchInfo(error), [error]);
  const chunkError = useMemo(() => isChunkLoadError(error), [error]);

  useEffect(() => {
    if (chunkError) {
      tryRecoverChunkLoadError(error);
    }
  }, [chunkError, error]);

  if (import.meta.env.DEV) {
    console.error("Route error:", error);
  }

  return (
    <div className="flex flex-col justify-center items-center min-h-[60vh] px-4 py-12">
      <div className="card max-w-lg w-full p-8 animate-fadeInUp">
        <div className="flex flex-col items-center text-center">
          <div className="mb-6 p-4 rounded-full bg-danger-100 dark:bg-danger-700/20">
            <FaExclamationTriangle className="w-16 h-16 text-danger-600 dark:text-danger-400" />
          </div>
          <h2 className="text-2xl md:text-3xl font-bold bg-gradient-to-r from-primary-600 to-secondary-600 bg-clip-text text-transparent dark:from-primary-400 dark:to-secondary-400 mb-3">
            Страница не загрузилась
          </h2>
          {chunkError ? (
            <div className="mb-6 p-4 rounded-lg bg-warning-50 dark:bg-warning-900/20 border border-warning-200 dark:border-warning-800 text-left">
              <p className="font-semibold text-warning-800 dark:text-warning-200 mb-1">
                Приложение было обновлено
              </p>
              <p className="text-sm text-warning-700 dark:text-warning-300">
                Нужна полная перезагрузка страницы, чтобы загрузить свежие
                файлы.
              </p>
            </div>
          ) : browserMismatch ? (
            <div className="mb-6 p-4 rounded-lg bg-warning-50 dark:bg-warning-900/20 border border-warning-200 dark:border-warning-800 text-left">
              <p className="font-semibold text-warning-800 dark:text-warning-200 mb-1">
                Браузер не подходит
              </p>
              <p className="text-sm text-warning-700 dark:text-warning-300 mb-1">
                {browserMismatch.reason}
              </p>
              <p className="text-sm text-warning-700 dark:text-warning-300">
                {browserMismatch.solution}
              </p>
            </div>
          ) : (
            <>
              <p className="text-gray-600 dark:text-gray-400 mb-4 leading-relaxed">
                Приложение не удалось загрузить эту страницу. Возможные причины:
              </p>
              <ul className="text-left text-gray-600 dark:text-gray-400 mb-6 space-y-2 text-sm">
                {FRIENDLY_HINTS.map((hint, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <FaCircle className="w-1.5 h-1.5 text-primary-500 mt-2 flex-shrink-0" />
                    <span>{hint}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="text-gray-500 dark:text-gray-500 text-sm mb-6">
            Если проблема повторяется — обратитесь в техподдержку.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 w-full sm:w-auto">
            <button
              type="button"
              onClick={() => {
                if (chunkError) {
                  forceHardReload();
                } else {
                  window.location.reload();
                }
              }}
              className="btn-primary flex items-center justify-center gap-2"
            >
              <FaRedo className="w-4 h-4" />
              {chunkError ? "Перезапустить приложение" : "Обновить страницу"}
            </button>
            <a
              href="/app"
              className="btn bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600 flex items-center justify-center gap-2"
            >
              <FaHome className="w-4 h-4" />
              На главную
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ErrorFallback;
