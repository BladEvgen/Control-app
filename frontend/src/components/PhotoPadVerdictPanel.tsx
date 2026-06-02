import React from "react";
import type { PhotoData } from "../schemas/IData";
import {
  buildPhotoPadVerdictDisplay,
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
        Вывод
      </p>
      <div className="mt-1 flex items-baseline justify-between gap-3">
        <p className={`text-sm font-semibold leading-snug ${riskClass}`}>
          {display.headline}
        </p>
        {display.riskPercent != null &&
        (display.variant === "suspicious" || display.variant === "review") ? (
          <span
            className={`shrink-0 text-sm font-bold tabular-nums ${riskClass}`}
          >
            {display.riskPercent}%
          </span>
        ) : null}
      </div>
      {display.summary ? (
        <p className="mt-1.5 text-xs leading-snug text-slate-600 dark:text-slate-300">
          {display.summary}
        </p>
      ) : null}
      {display.manualOverride ? (
        <p className="mt-1.5 text-[11px] text-slate-500 dark:text-slate-400">
          Решение оператора.
        </p>
      ) : null}
    </section>
  );
};

export default PhotoPadVerdictPanel;
