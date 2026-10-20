import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { FaCheck } from "react-icons/fa";
import axiosInstance from "../api";
import { humanizeApiError } from "./faceLabHumanMessages";
import { PoseGuide, type PoseGuidePose } from "./liveness";

const SAVE_FACE_SAMPLE_TIMEOUT_MS = 180_000;

const BOOTSTRAP_ANGLES = ["front", "left", "right"] as const;
export type BootstrapAngle = (typeof BOOTSTRAP_ANGLES)[number];

const ANGLE_HINTS: Record<BootstrapAngle, string> = {
  front: "Смотрите прямо в камеру, голову держите ровно.",
  left: "Немного поверните голову влево, как на рисунке. Не наклоняйте её.",
  right: "Немного поверните голову вправо, как на рисунке. Не наклоняйте её.",
};

const ANGLE_SHORT: Record<BootstrapAngle, string> = {
  front: "Прямо",
  left: "Влево",
  right: "Вправо",
};

const ANGLE_POSE: Record<BootstrapAngle, PoseGuidePose> = {
  front: "front",
  left: "turn_left",
  right: "turn_right",
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
          ? `Снимок «${ANGLE_SHORT[savedAngle]}» обновлён.`
          : afterThis >= BOOTSTRAP_ANGLES.length
            ? "Готово, все три снимка сохранены."
            : "Сохранено. Сделайте следующий снимок.",
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
        text: "Фото в профиле обновлено. Снимки для входа не менялись.",
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
      <div className="facelab-empty">
        <p className="facelab-empty-title">Сначала выберите сотрудника</p>
        <p>Потом снимем три положения головы: прямо, влево и вправо.</p>
      </div>
    );
  }

  const canRetake = Boolean(status && allDone && !inRetake);

  return (
    <section className="facelab-card" aria-labelledby="facelab-poses-title">
      <div className="facelab-card-head">
        <h2 id="facelab-poses-title" className="facelab-step-title">
          Три снимка для входа
        </h2>
        {status ? (
          <span className="facelab-count">
            {inRetake && retakeAngle
              ? `Пересъёмка: ${ANGLE_SHORT[retakeAngle]}`
              : `${completedSteps} из 3 готово`}
          </span>
        ) : null}
      </div>

      {statusError ? (
        <p className="facelab-note" data-tone="warning">
          {statusError}
        </p>
      ) : null}

      <ol className="facelab-poses">
        {BOOTSTRAP_ANGLES.map((a, i) => {
          const done = present.has(a);
          const active = showCaptureUi && workAngle === a;
          const body = (
            <>
              <span className="facelab-pose-art">
                <PoseGuide pose={ANGLE_POSE[a]} size={76} animate={active} />
                {done ? (
                  <span className="facelab-pose-check" aria-hidden>
                    <FaCheck />
                  </span>
                ) : null}
              </span>
              <span className="facelab-pose-name">
                {i + 1}. {ANGLE_SHORT[a]}
              </span>
              <span className="facelab-pose-state">
                {active
                  ? "Сейчас"
                  : done
                    ? canRetake
                      ? "Переснять"
                      : "Готово"
                    : "Ждёт"}
              </span>
            </>
          );
          return (
            <li
              key={a}
              className="facelab-pose"
              data-active={active || undefined}
              data-done={done || undefined}
            >
              {canRetake ? (
                <button
                  type="button"
                  className="facelab-pose-inner"
                  onClick={() => setRetakeAngle(a)}
                  aria-label={`Переснять снимок «${ANGLE_SHORT[a]}»`}
                >
                  {body}
                </button>
              ) : (
                <div
                  className="facelab-pose-inner"
                  aria-current={active ? "step" : undefined}
                >
                  {body}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      {canRetake ? (
        <p className="facelab-note" data-tone="success">
          Все три снимка сохранены. Чтобы заменить один, нажмите на него.
        </p>
      ) : null}

      {showCaptureUi && workAngle ? (
        <p className="facelab-instruction">{ANGLE_HINTS[workAngle]}</p>
      ) : null}

      {banner ? (
        <p
          className="facelab-note"
          data-tone={banner.ok ? "success" : "danger"}
          role="status"
        >
          {banner.text}
        </p>
      ) : null}

      {showCaptureUi && workAngle ? (
        <div className="facelab-actions-col">
          <button
            type="button"
            className="ws-btn-primary facelab-btn-lg"
            disabled={busy || !file}
            onClick={() => void saveSample()}
          >
            {busy
              ? "Сохраняем…"
              : file
                ? inRetake
                  ? `Сохранить новый снимок «${ANGLE_SHORT[workAngle]}»`
                  : `Сохранить «${ANGLE_SHORT[workAngle]}» и продолжить`
                : "Сначала сделайте снимок"}
          </button>
          {inRetake ? (
            <button
              type="button"
              className="ws-btn-ghost facelab-btn-lg"
              disabled={busy}
              onClick={() => {
                setRetakeAngle(null);
                setBanner(null);
              }}
            >
              Отменить пересъёмку
            </button>
          ) : null}
        </div>
      ) : null}

      <details className="facelab-details">
        <summary>Фото в профиле сотрудника</summary>
        <div className="facelab-actions-col">
          <button
            type="button"
            className="ws-btn-ghost"
            disabled={busy || !file}
            onClick={() => void uploadAvatarOnly()}
          >
            Поставить текущий снимок в профиль
          </button>
          {lastSampleId ? (
            <button
              type="button"
              className="ws-btn-ghost"
              disabled={busy}
              onClick={() => void applyAvatar()}
            >
              Поставить последний сохранённый снимок в профиль
            </button>
          ) : null}
        </div>
      </details>
    </section>
  );
}
