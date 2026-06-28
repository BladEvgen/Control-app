import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import axiosInstance from "../api";
import { humanizeApiError } from "./faceLabHumanMessages";
import { faceLabSpring } from "./faceLabDesignTokens";

const smoothEase = [0.22, 1, 0.36, 1] as const;

const SAVE_FACE_SAMPLE_TIMEOUT_MS = 180_000;

const BOOTSTRAP_ANGLES = ["front", "left", "right"] as const;
export type BootstrapAngle = (typeof BOOTSTRAP_ANGLES)[number];

const ANGLE_HINTS: Record<BootstrapAngle, string> = {
  front: "Смотрите прямо в камеру, без поворота головы.",
  left: "Повернитесь левым ухом к камере. Голову не наклоняйте.",
  right: "Повернитесь правым ухом к камере. Голову не наклоняйте.",
};

const ANGLE_STEP_TITLES: Record<BootstrapAngle, string> = {
  front: "Шаг 1",
  left: "Шаг 2",
  right: "Шаг 3",
};

const ANGLE_SHORT: Record<BootstrapAngle, string> = {
  front: "Прямо",
  left: "Влево",
  right: "Вправо",
};

export type FaceLabBootstrapStatus = {
  pin: string;
  angles_present: string[];
  angles_required?: string[];
  angles_missing?: string[];
  next_angle?: string | null;
  bootstrap_complete?: boolean;
  active_count: number;
  max_active_samples: number;
  face_profile_state: string;
  has_avatar?: boolean;
  cold_start_note?: string;
};

type Props = {
  pin: string;
  file: File | null;
  onSaved: () => void;
  onAvatarUpdated?: () => void;
  onCameraGuidanceAngleChange?: (angle: BootstrapAngle | null) => void;
};

function doneCount(present: Set<string>): number {
  return BOOTSTRAP_ANGLES.filter((a) => present.has(a)).length;
}

function StepDot({
  n,
  active,
  done,
}: {
  n: number;
  active: boolean;
  done: boolean;
}) {
  return (
    <motion.div
      layout
      transition={faceLabSpring}
      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold ${
        done
          ? "bg-emerald-500 text-white shadow-md shadow-emerald-500/30"
          : active
            ? "bg-blue-600 text-white shadow-md shadow-blue-600/25 ring-4 ring-blue-200/50 dark:bg-blue-500 dark:ring-blue-500/25"
            : "border-2 border-slate-200 bg-white text-slate-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-500"
      }`}
    >
      {done ? "✓" : n}
    </motion.div>
  );
}

export function FaceLabBootstrapPanel({
  pin,
  file,
  onSaved,
  onAvatarUpdated,
  onCameraGuidanceAngleChange,
}: Props) {
  const [status, setStatus] = useState<FaceLabBootstrapStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<{ ok: boolean; text: string } | null>(
    null,
  );
  const [lastSampleId, setLastSampleId] = useState<number | null>(null);
  const [retakeAngle, setRetakeAngle] = useState<BootstrapAngle | null>(null);

  const refreshStatus = useCallback(async () => {
    if (!pin) {
      setStatus(null);
      return;
    }
    setStatusError(null);
    try {
      const res = await axiosInstance.get<FaceLabBootstrapStatus>(
        `face-lab/bootstrap-status/?pin=${encodeURIComponent(pin)}`,
      );
      setStatus(res.data);
    } catch {
      setStatus(null);
      setStatusError("Не удалось загрузить прогресс. Обновите страницу.");
    }
  }, [pin]);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  const present = useMemo(() => {
    const s = new Set(
      (status?.angles_present ?? []).map((a) => String(a).trim().toLowerCase()),
    );
    return s;
  }, [status]);

  const nextAngle = useMemo((): BootstrapAngle | null => {
    const fromApi = status?.next_angle;
    if (fromApi === "front" || fromApi === "left" || fromApi === "right") {
      return fromApi;
    }
    for (const a of BOOTSTRAP_ANGLES) {
      if (!present.has(a)) return a;
    }
    return null;
  }, [status, present]);

  const allDone =
    status?.bootstrap_complete === true ||
    (nextAngle === null && pin && status !== null);

  const workAngle = retakeAngle ?? nextAngle;
  const inRetake = retakeAngle !== null;
  const showCaptureUi = Boolean(pin && workAngle && (!allDone || inRetake));

  useEffect(() => {
    if (!onCameraGuidanceAngleChange) return;
    if (!pin || !workAngle || (!inRetake && allDone)) {
      onCameraGuidanceAngleChange(null);
    } else {
      onCameraGuidanceAngleChange(workAngle);
    }
  }, [pin, allDone, workAngle, inRetake, onCameraGuidanceAngleChange]);

  const completedSteps = doneCount(present);
  const progressFraction = completedSteps / BOOTSTRAP_ANGLES.length;
  const currentStepIndex = workAngle
    ? BOOTSTRAP_ANGLES.indexOf(workAngle)
    : completedSteps >= 3
      ? 3
      : completedSteps;

  const saveSample = async () => {
    setBanner(null);
    if (!pin || !file || !workAngle) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("pin", pin);
      fd.append("angle", workAngle);
      fd.append("source", "bootstrap_capture");
      fd.append("image", file);
      const res = await axiosInstance.post<{
        ok?: boolean;
        sample_id?: number;
        message?: string;
      }>("face-lab/save-face-sample/", fd, {
        timeout: SAVE_FACE_SAMPLE_TIMEOUT_MS,
      });
      const sid =
        typeof res.data?.sample_id === "number" ? res.data.sample_id : null;
      setLastSampleId(sid);
      const wasRetake = inRetake;
      const savedAngle = workAngle;
      const afterThis = wasRetake
        ? BOOTSTRAP_ANGLES.length
        : doneCount(present) + 1;
      setRetakeAngle(null);
      setBanner({
        ok: true,
        text: wasRetake
          ? `Ракурс «${ANGLE_SHORT[savedAngle]}» обновлён.`
          : afterThis >= BOOTSTRAP_ANGLES.length
            ? "Готово — все три ракурса сохранены."
            : "Сохранено. Снимите следующий кадр.",
      });
      onSaved();
      await refreshStatus();
    } catch (e: unknown) {
      let raw = "Не удалось сохранить кадр.";
      if (axios.isAxiosError(e) && e.response?.data) {
        const d = e.response.data;
        if (typeof d === "object" && d !== null && "error" in d) {
          raw = String((d as { error: string }).error);
        }
      } else if (e instanceof Error) {
        raw = e.message;
      }
      const f = humanizeApiError(raw);
      setBanner({
        ok: false,
        text: [f.title, f.detail].filter(Boolean).join(" "),
      });
    } finally {
      setBusy(false);
    }
  };

  const uploadAvatarOnly = async () => {
    setBanner(null);
    if (!pin || !file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("image", file);
      await axiosInstance.put(`staff/${encodeURIComponent(pin)}/avatar/`, fd);
      setBanner({
        ok: true,
        text: "Фото в профиле обновлено. Ракурсы для входа не менялись.",
      });
      await refreshStatus();
      onAvatarUpdated?.();
    } catch (e: unknown) {
      let raw = "Не удалось обновить фото профиля.";
      if (axios.isAxiosError(e) && e.response?.data) {
        const d = e.response.data;
        if (typeof d === "object" && d !== null && "error" in d) {
          raw = String((d as { error: string }).error);
        }
      }
      const f = humanizeApiError(raw);
      setBanner({
        ok: false,
        text: [f.title, f.detail].filter(Boolean).join(" "),
      });
    } finally {
      setBusy(false);
    }
  };

  const applyAvatar = async () => {
    setBanner(null);
    if (!pin || !lastSampleId) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("pin", pin);
      fd.append("sample_id", String(lastSampleId));
      const res = await axiosInstance.post<{ message?: string }>(
        "face-lab/apply-sample-avatar/",
        fd,
      );
      setBanner({
        ok: true,
        text: res.data?.message?.trim() || "Это фото теперь в профиле.",
      });
      await refreshStatus();
      onAvatarUpdated?.();
    } catch (e: unknown) {
      let raw = "Не удалось обновить фото в профиле.";
      if (axios.isAxiosError(e) && e.response?.data) {
        const d = e.response.data;
        if (typeof d === "object" && d !== null && "error" in d) {
          raw = String((d as { error: string }).error);
        }
      }
      const f = humanizeApiError(raw);
      setBanner({
        ok: false,
        text: [f.title, f.detail].filter(Boolean).join(" "),
      });
    } finally {
      setBusy(false);
    }
  };

  if (!pin) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/80 px-4 py-6 text-center dark:border-slate-600 dark:bg-slate-900/40">
        <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
          Сначала выберите сотрудника
        </p>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          Дальше откроются три шага съёмки.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200/80 bg-white/90 px-3 py-4 dark:border-slate-600/60 dark:bg-slate-900/50 sm:px-4 sm:py-5">
      <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-50">
            Три кадра для входа
          </h3>
          <p className="mt-0.5 max-w-md text-xs text-slate-600 dark:text-slate-400">
            Сохраните прямо, влево и вправо.
          </p>
        </div>
        {status && (!allDone || inRetake) ? (
          <p className="text-xs font-medium text-blue-700 dark:text-blue-300">
            {inRetake && retakeAngle
              ? `Пересъёмка: ${ANGLE_SHORT[retakeAngle]}`
              : `Шаг ${Math.min(currentStepIndex + 1, 3)} из 3`}
          </p>
        ) : null}
      </div>

      {statusError ? (
        <p className="mb-4 text-sm text-amber-800 dark:text-amber-200">
          {statusError}
        </p>
      ) : null}

      {status && (!allDone || inRetake) ? (
        <div className="mb-6">
          <div className="mb-3 flex w-full items-center">
            {BOOTSTRAP_ANGLES.map((a, i) => (
              <div key={a} className="flex min-w-0 flex-1 items-center">
                <StepDot
                  n={i + 1}
                  done={present.has(a)}
                  active={workAngle === a}
                />
                {i < BOOTSTRAP_ANGLES.length - 1 ? (
                  <div
                    className={`mx-1.5 h-1 min-w-[12px] flex-1 rounded-full sm:mx-2 ${
                      present.has(a)
                        ? "bg-emerald-400"
                        : "bg-slate-200 dark:bg-slate-600"
                    }`}
                  />
                ) : null}
              </div>
            ))}
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
            <motion.div
              className="h-full rounded-full bg-blue-600 dark:bg-blue-500"
              initial={false}
              animate={{ width: `${progressFraction * 100}%` }}
              transition={{ duration: 0.4, ease: smoothEase }}
            />
          </div>
          <p className="mt-2 text-center text-xs text-slate-500 dark:text-slate-400">
            {completedSteps} из 3 готово
          </p>
        </div>
      ) : null}

      {status && allDone && !inRetake ? (
        <div className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50/95 px-4 py-4 dark:border-emerald-800/50 dark:bg-emerald-950/40">
          <p className="font-semibold text-emerald-950 dark:text-emerald-100">
            Все шаги пройдены
          </p>
          <p className="mt-1 text-sm leading-relaxed text-emerald-900/90 dark:text-emerald-200/90">
            Три ракурса уже сохранены. При необходимости можно переснять любой.
          </p>
        </div>
      ) : null}

      {status && allDone && !inRetake ? (
        <div className="mb-6 flex flex-col gap-2 rounded-xl border border-slate-200/90 bg-slate-50/90 px-4 py-3 dark:border-slate-600/60 dark:bg-slate-800/40">
          <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
            Заменить эталонный ракурс
          </p>
          <p className="text-xs text-slate-600 dark:text-slate-400">
            Можно переснять любой из трёх кадров: новый снимок заменит текущий
            активный образец для этого ракурса.
          </p>
          <div className="flex flex-wrap gap-2">
            {BOOTSTRAP_ANGLES.map((a) => (
              <button
                key={a}
                type="button"
                onClick={() => setRetakeAngle(a)}
                className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800 shadow-sm transition hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
              >
                Переснять — {ANGLE_SHORT[a]}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {showCaptureUi && workAngle ? (
        <div className="mb-5 rounded-lg border border-slate-200/90 bg-slate-50/90 px-3 py-3 dark:border-slate-600/70 dark:bg-slate-800/40 sm:px-4 sm:py-4">
          <p className="text-base font-semibold text-slate-900 dark:text-slate-50">
            {ANGLE_STEP_TITLES[workAngle]}: {ANGLE_SHORT[workAngle]}
          </p>
          <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
            {ANGLE_HINTS[workAngle]}
          </p>
        </div>
      ) : null}

      {banner ? (
        <div
          className={`mb-5 rounded-xl border px-4 py-3 text-sm ${
            banner.ok
              ? "border-emerald-200 bg-emerald-50 text-emerald-950 dark:border-emerald-800/50 dark:bg-emerald-950/35 dark:text-emerald-100"
              : "border-rose-200 bg-rose-50 text-rose-950 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-100"
          }`}
          role="status"
        >
          {banner.text}
        </div>
      ) : null}

      {showCaptureUi && workAngle ? (
        <div className="space-y-4">
          <button
            type="button"
            disabled={busy || !file}
            onClick={() => void saveSample()}
            className="w-full rounded-xl bg-blue-600 py-3.5 text-base font-semibold text-white shadow-lg shadow-blue-600/25 transition hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/70 focus-visible:ring-offset-2 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:opacity-45 dark:bg-blue-500 dark:hover:bg-blue-600 dark:focus-visible:ring-blue-300/80 dark:focus-visible:ring-offset-slate-950"
          >
            {busy
              ? "Сохраняем…"
              : file
                ? inRetake
                  ? `Сохранить новый «${ANGLE_SHORT[workAngle]}»`
                  : `Сохранить «${ANGLE_SHORT[workAngle]}» и продолжить`
                : "Сначала сделайте снимок"}
          </button>

          {inRetake ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setRetakeAngle(null);
                setBanner(null);
              }}
              className="w-full rounded-xl border border-slate-300 bg-white py-3 text-sm font-medium text-slate-800 transition hover:bg-slate-50 disabled:opacity-45 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
            >
              Отменить пересъёмку
            </button>
          ) : null}

          <details className="group rounded-xl border border-slate-200/90 bg-slate-50/80 dark:border-slate-600/60 dark:bg-slate-900/40">
            <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-700 outline-none marker:content-none dark:text-slate-200 [&::-webkit-details-marker]:hidden">
              <span className="flex items-center justify-between gap-2">
                Дополнительно
                <span className="text-slate-400 transition group-open:rotate-180">
                  ▼
                </span>
              </span>
            </summary>
            <div className="space-y-2 border-t border-slate-200/80 px-4 pb-4 pt-3 dark:border-slate-600/50">
              <button
                type="button"
                disabled={busy || !file}
                onClick={() => void uploadAvatarOnly()}
                className="w-full rounded-lg border border-slate-200 bg-white py-2.5 text-sm font-medium text-slate-800 transition hover:bg-slate-50 disabled:opacity-45 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
              >
                Только обновить фото в профиле
              </button>
              <button
                type="button"
                disabled={busy || !lastSampleId}
                onClick={() => void applyAvatar()}
                className="w-full rounded-lg py-2.5 text-sm font-medium text-blue-700 transition hover:bg-blue-50 hover:text-blue-800 disabled:opacity-45 dark:text-blue-300 dark:hover:bg-blue-500/10 dark:hover:text-blue-200"
              >
                Поставить последний кадр в профиль
              </button>
            </div>
          </details>
        </div>
      ) : allDone && !inRetake ? (
        <details className="rounded-xl border border-slate-200/90 bg-slate-50/80 dark:border-slate-600/60 dark:bg-slate-900/40">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-700 dark:text-slate-200 [&::-webkit-details-marker]:hidden">
            Обновить фото профиля отдельно
          </summary>
          <div className="space-y-2 border-t border-slate-200/80 px-4 pb-4 pt-3 dark:border-slate-600/50">
            <button
              type="button"
              disabled={busy || !file}
              onClick={() => void uploadAvatarOnly()}
              className="w-full rounded-lg border border-slate-200 bg-white py-2.5 text-sm font-medium text-slate-800 transition hover:bg-slate-50 disabled:opacity-45 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
            >
              Загрузить новый снимок в профиль
            </button>
            {lastSampleId ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => void applyAvatar()}
                className="w-full rounded-lg py-2.5 text-sm font-medium text-blue-700 transition hover:bg-blue-50 hover:text-blue-800 dark:text-blue-300 dark:hover:bg-blue-500/10 dark:hover:text-blue-200"
              >
                Взять последний сохранённый кадр для профиля
              </button>
            ) : null}
          </div>
        </details>
      ) : null}
    </div>
  );
}
