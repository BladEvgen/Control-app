import React from "react";
import type { PhotoData } from "../schemas/IData";
import {
  buildPhotoPadVerdictDisplay,
  photoPadVerdictBarClass,
  photoPadVerdictPanelClass,
  photoPadVerdictRiskClass,
} from "../utils/photoPadVerdict";

type PhotoPadVerdictPanelProps = {
  photo: Partial<PhotoData>;
  effectiveStatus: NonNullable<PhotoData["photoSpoofStatus"]> | "pending";
  className?: string;
};

export const PhotoPadVerdictPanel: React.FC<PhotoPadVerdictPanelProps> = ({
  photo,
  effectiveStatus,
  className = "",
}) => {
  const display = buildPhotoPadVerdictDisplay(photo, effectiveStatus);
  const panelClass = photoPadVerdictPanelClass(display.variant);
  const riskClass = photoPadVerdictRiskClass(display.variant);

  return (
    <section
      className={`rounded-xl border px-3 py-2.5 shadow-sm ${panelClass} ${className}`}
      aria-label="Вывод автопроверки"
    >
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
        {display.manualOverride ? "Решил оператор" : "Решено автоматически"}
      </p>
      <p className={`mt-1 text-sm font-semibold leading-snug ${riskClass}`}>
        {display.headline}
      </p>
      {display.summary ? (
        <p className="mt-1.5 text-xs leading-snug text-slate-600 dark:text-slate-300">
          {display.summary}
        </p>
      ) : null}
      {!display.manualOverride && display.riskPercent != null ? (
        <div className="mt-2">
          <div className="flex items-baseline justify-between text-[11px] text-slate-500 dark:text-slate-400">
            <span>Вероятность подмены</span>
            <span className={`font-semibold tabular-nums ${riskClass}`}>
              {display.riskPercent}%
            </span>
          </div>
          <div
            className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-200/80 dark:bg-slate-700/70"
            role="meter"
            aria-label="Вероятность подмены"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={display.riskPercent}
          >
            <div
              className={`h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none ${photoPadVerdictBarClass(display.variant)}`}
              style={{ width: `${Math.max(2, display.riskPercent)}%` }}
            />
          </div>
        </div>
      ) : null}
      {display.autoNote ? (
        <p className="mt-1.5 text-[11px] text-slate-500 dark:text-slate-400">
          {display.autoNote}
        </p>
      ) : null}
    </section>
  );
};

export default PhotoPadVerdictPanel;
