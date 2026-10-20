import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import axios from "axios";
import {
  FaCircleNotch,
  FaSearch,
  FaUserCheck,
  FaUserPlus,
} from "react-icons/fa";
import axiosInstance, { getCookie } from "../api";
import { apiUrl } from "../../apiConfig";
import LoaderComponent from "../components/LoaderComponent";
import { installFaceLabAxiosLogging } from "../faceLab/faceLabAxiosLogging";
import FaceCameraOverlay from "../faceLab/camera/FaceCameraOverlay";
import type {
  CameraGuidanceContext,
  FaceCameraOverlayRef,
} from "../faceLab/camera/types";
import { parsePadResult } from "../faceLab/faceLabApi";
import {
  PadResultPanel,
  RecognizeOrRaw,
  VerifyOrRaw,
  type PadTestResponse,
} from "../faceLab/FaceLabResultPanels";
import { FaceLabConsentDialog } from "../faceLab/FaceLabConsentDialogs";
import {
  persistFileConsent,
  readFileConsent,
} from "../faceLab/faceLabConsentStorage";
import {
  humanizeApiError,
  humanizePadFailureReason,
} from "../faceLab/faceLabHumanMessages";
import {
  FaceLabStaffCombobox,
  type StaffPickOption,
} from "../faceLab/FaceLabStaffCombobox";
import {
  FaceLabBootstrapPanel,
  type BootstrapAngle,
} from "../faceLab/FaceLabBootstrapPanel";
import { FaceLabCapture } from "../faceLab/FaceLabCapture";
import { FaceLabVoiceSwitch } from "../faceLab/FaceLabVoiceSwitch";
import {
  readVoiceLang,
  persistVoiceLang,
  warmFaceLabTtsVoicePack,
  type FaceLabVoiceLang,
} from "../faceLab/faceLabCameraVoice";

installFaceLabAxiosLogging(axiosInstance);

type LabMode = "search" | "compare" | "bootstrap";

const FACE_LAB_HEAVY_REQUEST_MS = 180_000;

type FaceLabStaffOptionRow = {
  pin: string;
  fio: string;
  dept_id: number;
  dept_name: string;
  face_profile_state?: string;
};

const MODES: {
  id: LabMode;
  title: string;
  hint: string;
  icon: React.ReactNode;
}[] = [
  {
    id: "search",
    title: "Поиск",
    hint: "Кто на фото: ищем по всей базе",
    icon: <FaSearch aria-hidden />,
  },
  {
    id: "compare",
    title: "Сверка",
    hint: "Тот ли это человек: сравниваем с одним сотрудником",
    icon: <FaUserCheck aria-hidden />,
  },
  {
    id: "bootstrap",
    title: "Настройка",
    hint: "Три снимка сотрудника для входа по лицу",
    icon: <FaUserPlus aria-hidden />,
  },
];

function authBearerHeaders(): Record<string, string> {
  const t = getCookie("access_token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

function StepTitle({ n, children }: { n?: number; children: React.ReactNode }) {
  return (
    <h2 className="facelab-step-title">
      {n ? <span className="facelab-step-no">{n}</span> : null}
      {children}
    </h2>
  );
}

const reveal = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
  transition: { duration: 0.24, ease: [0.22, 1, 0.36, 1] as const },
};

const FaceLabPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const urlBootstrapAppliedRef = useRef(false);
  const [mode, setMode] = useState<LabMode>("search");
  const [allStaffFlat, setAllStaffFlat] = useState<StaffPickOption[]>([]);
  const [allStaffLoading, setAllStaffLoading] = useState(false);
  const [staffListError, setStaffListError] = useState<string | null>(null);
  const [staffSearchFocusTick, setStaffSearchFocusTick] = useState(0);
  const [selectedPin, setSelectedPin] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [padResult, setPadResult] = useState<PadTestResponse | null>(null);
  const [padWarning, setPadWarning] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const cameraRef = useRef<FaceCameraOverlayRef>(null);
  const [bootstrapAngle, setBootstrapAngle] = useState<BootstrapAngle | null>(
    null,
  );
  const fileInputRef = useRef<HTMLInputElement>(null);
  const resultRef = useRef<HTMLElement>(null);
  const [fileConsentDone, setFileConsentDone] = useState(readFileConsent);
  const [fileConsentOpen, setFileConsentOpen] = useState(false);
  const [pendingDrop, setPendingDrop] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [voiceLang, setVoiceLang] = useState<FaceLabVoiceLang>(readVoiceLang);

  useEffect(() => {
    persistVoiceLang(voiceLang);
    if (voiceLang !== "off") void warmFaceLabTtsVoicePack(voiceLang);
  }, [voiceLang]);

  useEffect(() => {
    if (urlBootstrapAppliedRef.current) return;
    const b = (searchParams.get("bootstrap") || "").trim().toLowerCase();
    if (b === "1" || b === "true" || b === "yes") {
      urlBootstrapAppliedRef.current = true;
      setMode("bootstrap");
      const p = (searchParams.get("pin") || "").trim();
      if (p) setSelectedPin(p);
    }
  }, [searchParams]);

  useEffect(() => {
    if (mode !== "bootstrap") setBootstrapAngle(null);
  }, [mode]);

  const guidanceContext = useMemo((): CameraGuidanceContext => {
    if (mode !== "bootstrap") return "profile_photo";
    return bootstrapAngle ? `bootstrap_${bootstrapAngle}` : "default";
  }, [mode, bootstrapAngle]);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const clearResults = useCallback(() => {
    setPadResult(null);
    setPadWarning(null);
    setVerifyResult(null);
  }, []);

  const takeFile = useCallback(
    (f: File | null) => {
      setFile(f);
      if (f) clearResults();
    },
    [clearResults],
  );

  const onCameraShot = useCallback(
    (blob: Blob) =>
      takeFile(
        new File(
          [blob],
          `face-lab-${new Date().toISOString().replace(/[:.]/g, "-")}.jpg`,
          {
            type: blob.type || "image/jpeg",
          },
        ),
      ),
    [takeFile],
  );

  useEffect(() => {
    if (mode === "search") {
      setAllStaffFlat([]);
      setStaffListError(null);
      setAllStaffLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setAllStaffLoading(true);
      setStaffListError(null);
      try {
        const res = await axiosInstance.get<FaceLabStaffOptionRow[]>(
          "face-lab/staff-options/",
        );
        if (cancelled) return;
        const byPin = new Map<string, StaffPickOption>();
        for (const row of Array.isArray(res.data) ? res.data : []) {
          const pin = String(row.pin ?? "").trim();
          if (!pin || byPin.has(pin)) continue;
          const fps =
            typeof row.face_profile_state === "string"
              ? row.face_profile_state.trim()
              : "";
          byPin.set(pin, {
            pin,
            fio: (row.fio ?? "").trim() || "Без ФИО",
            deptName: (row.dept_name ?? "").trim() || "Отдел",
            deptId: row.dept_id,
            faceProfileState: fps || undefined,
          });
        }
        const flat = Array.from(byPin.values()).sort(
          (a, b) =>
            a.fio.localeCompare(b.fio, "ru") ||
            a.deptName.localeCompare(b.deptName, "ru"),
        );
        setAllStaffFlat(flat);
        if (flat.length > 0) setStaffSearchFocusTick((t) => t + 1);
      } catch {
        if (!cancelled) {
          setStaffListError(
            "Список сотрудников не загрузился. Обновите страницу или проверьте сеть.",
          );
          setAllStaffFlat([]);
        }
      } finally {
        if (!cancelled) setAllStaffLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mode]);

  const afterBootstrapSave = useCallback(() => {
    setFile(null);
    setFileInputKey((k) => k + 1);
    clearResults();
    setError(null);
    cameraRef.current?.resetSession();
  }, [clearResults]);

  const switchMode = (next: LabMode) => {
    if (next === mode) return;
    setMode(next);
    clearResults();
    setError(null);
    setFile(null);
    setFileInputKey((k) => k + 1);
    setSelectedPin("");
    cameraRef.current?.resetSession();
  };

  const requestOpenCamera = useCallback(
    () => void cameraRef.current?.open("user"),
    [],
  );

  const requestPickFile = useCallback(() => {
    if (!fileConsentDone) {
      setFileConsentOpen(true);
      return;
    }
    fileInputRef.current?.click();
  }, [fileConsentDone]);

  const onDropFile = useCallback(
    (f: File) => {
      if (fileConsentDone) takeFile(f);
      else {
        setPendingDrop(f);
        setFileConsentOpen(true);
      }
    },
    [fileConsentDone, takeFile],
  );

  const confirmFileConsent = useCallback(() => {
    persistFileConsent();
    setFileConsentDone(true);
    setFileConsentOpen(false);
    if (pendingDrop) {
      takeFile(pendingDrop);
      setPendingDrop(null);
    } else {
      setTimeout(() => fileInputRef.current?.click(), 0);
    }
  }, [pendingDrop, takeFile]);

  const onSubmit = async () => {
    setError(null);
    clearResults();
    if (!file) {
      setError("Сначала снимите фото камерой или выберите файл на устройстве.");
      return;
    }
    if (mode === "compare" && !selectedPin) {
      setError("Для сверки выберите сотрудника в поле поиска.");
      return;
    }
    setBusy(true);
    let padLocal: PadTestResponse | null = null;
    try {
      const headers = authBearerHeaders();
      if (mode === "search") {
        const padFd = new FormData();
        padFd.append("image", file);
        const padRes = await axiosInstance.post("face-lab/pad-test/", padFd, {
          timeout: FACE_LAB_HEAVY_REQUEST_MS,
        });
        padLocal = parsePadResult(padRes.data);
        if (padLocal) setPadResult(padLocal);
        else {
          setPadWarning("Не удалось разобрать результат проверки фото.");
        }
        if (padLocal?.decision === "YES") {
          const fd = new FormData();
          fd.append("image", file);
          const res = await axios.post(`${apiUrl}/recognize-faces/`, fd, {
            headers,
            timeout: FACE_LAB_HEAVY_REQUEST_MS,
          });
          setVerifyResult(res.data);
        }
      } else {
        const vfd = new FormData();
        vfd.append("image", file);
        vfd.append("pin", selectedPin);
        const res = await axios.post(`${apiUrl}/verify-face/`, vfd, {
          headers,
          timeout: FACE_LAB_HEAVY_REQUEST_MS,
        });
        setVerifyResult(res.data);
      }
    } catch (err: unknown) {
      if (
        axios.isAxiosError(err) &&
        err.response?.data &&
        typeof err.response.data === "object"
      ) {
        setVerifyResult(err.response.data);
      } else {
        setVerifyResult(null);
        setError(err instanceof Error ? err.message : "Запрос не удался.");
      }
    } finally {
      setBusy(false);
    }
  };

  const spoofed = mode === "search" && padResult?.decision === "NO";

  useEffect(() => {
    if (
      !busy &&
      (verifyResult !== null || spoofed) &&
      window.matchMedia("(max-width: 1100px)").matches
    ) {
      resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [busy, verifyResult, spoofed]);

  const errorFriendly = error ? humanizeApiError(error) : null;
  const padWarningFriendly = padWarning
    ? humanizePadFailureReason(padWarning)
    : null;
  const staffListErrorFriendly = staffListError
    ? humanizeApiError(staffListError)
    : null;
  const needsStaff = mode !== "search";
  const activeMode = MODES.find((m) => m.id === mode)!;
  const hasResult = verifyResult !== null || spoofed;

  return (
    <section className="facelab">
      <header className="detail-head">
        <div className="ws-page-head">
          <h1>Face Lab</h1>
          <p className="detail-meta">
            Проверка живого лица, поиск по базе и сверка с эталоном.
          </p>
        </div>
        <div className="detail-actions">
          <FaceLabVoiceSwitch value={voiceLang} onChange={setVoiceLang} />
        </div>
      </header>

      <div className="facelab-modes-row">
        <div className="facelab-modes" role="group" aria-label="Режим работы">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              aria-pressed={mode === m.id}
              onClick={() => switchMode(m.id)}
            >
              {m.icon}
              {m.title}
            </button>
          ))}
        </div>
        <p className="facelab-mode-hint">{activeMode.hint}</p>
      </div>

      <FaceCameraOverlay
        ref={cameraRef}
        onShot={onCameraShot}
        requireLiveness={mode !== "bootstrap"}
        voiceLang={voiceLang}
        guidanceContext={guidanceContext}
      />

      <FaceLabConsentDialog
        open={fileConsentOpen}
        title="Фото с устройства"
        onCancel={() => {
          setFileConsentOpen(false);
          setPendingDrop(null);
        }}
        onConfirm={confirmFileConsent}
        confirmLabel="Продолжить"
      >
        <p>
          Фото уйдёт на сервер только после того, как вы нажмёте кнопку
          проверки.
        </p>
      </FaceLabConsentDialog>

      <input
        ref={fileInputRef}
        key={fileInputKey}
        type="file"
        accept="image/png,image/jpeg,.png,.jpg,.jpeg"
        className="sr-only"
        tabIndex={-1}
        aria-label="Выбор фото для проверки"
        onChange={(e) => takeFile(e.target.files?.[0] ?? null)}
      />

      <div className="facelab-layout">
        <div className="facelab-work">
          {needsStaff ? (
            <section className="facelab-card">
              <StepTitle n={1}>
                {mode === "bootstrap" ? "Кого настраиваем" : "Кого сверяем"}
              </StepTitle>
              {staffListError ? (
                <p className="facelab-note" data-tone="warning">
                  <strong>
                    {staffListErrorFriendly?.title ?? staffListError}
                  </strong>
                  {staffListErrorFriendly?.detail
                    ? ` ${staffListErrorFriendly.detail}`
                    : null}
                </p>
              ) : allStaffLoading ? (
                <LoaderComponent
                  fullscreen={false}
                  compact
                  inline
                  variant="bars"
                  showGlow={false}
                  message="Загружаем список сотрудников…"
                  className="justify-start py-2"
                />
              ) : allStaffFlat.length === 0 ? (
                <p className="facelab-note">
                  Нет сотрудников с привязкой к отделу. Проверьте права или
                  настройки.
                </p>
              ) : (
                <FaceLabStaffCombobox
                  options={allStaffFlat}
                  value={selectedPin}
                  onChange={setSelectedPin}
                  focusRequestId={staffSearchFocusTick}
                  label="ФИО, PIN или отдел"
                  emptyResultText="Ничего не нашли. Попробуйте ФИО, PIN или отдел."
                />
              )}
            </section>
          ) : null}

          <section className="facelab-card">
            <StepTitle n={needsStaff ? 2 : undefined}>Снимок</StepTitle>
            {mode === "bootstrap" ? null : (
              <p className="facelab-card-hint">
                Камера даст пару простых заданий и снимет кадр сама.
              </p>
            )}
            <FaceLabCapture
              file={file}
              previewUrl={previewUrl}
              onOpenCamera={requestOpenCamera}
              onPickFile={requestPickFile}
              onDropFile={onDropFile}
              submit={
                mode === "bootstrap"
                  ? undefined
                  : {
                      label:
                        mode === "search"
                          ? "Найти в базе"
                          : "Сверить с эталоном",
                      busyLabel:
                        mode === "search" ? "Ищем по базе…" : "Сверяем…",
                      busy,
                      onClick: () => void onSubmit(),
                    }
              }
            />
          </section>
        </div>

        <aside
          className="facelab-result"
          aria-label="Результат"
          ref={resultRef}
        >
          {mode === "bootstrap" ? (
            <FaceLabBootstrapPanel
              pin={selectedPin}
              file={file}
              onSaved={afterBootstrapSave}
              onCameraGuidanceAngleChange={setBootstrapAngle}
            />
          ) : busy ? (
            <p className="facelab-result-empty" data-busy role="status">
              <FaCircleNotch className="animate-spin" aria-hidden />
              {mode === "search"
                ? "Проверяем фото и ищем в базе…"
                : "Проверяем фото и сверяем…"}
            </p>
          ) : !hasResult && !errorFriendly && !padWarningFriendly ? (
            <p className="facelab-result-empty">
              Результат появится здесь после проверки.
            </p>
          ) : null}

          <AnimatePresence initial={false}>
            {padWarningFriendly ? (
              <motion.p
                key="pad-warning"
                className="facelab-note"
                data-tone="warning"
                {...reveal}
              >
                <strong>{padWarningFriendly.title}</strong>
                {padWarningFriendly.detail
                  ? ` ${padWarningFriendly.detail}`
                  : null}
              </motion.p>
            ) : null}
            {errorFriendly ? (
              <motion.p
                key="error"
                className="facelab-note"
                data-tone="warning"
                {...reveal}
              >
                <strong>{errorFriendly.title}</strong>
                {errorFriendly.detail ? ` ${errorFriendly.detail}` : null}
              </motion.p>
            ) : null}
            {verifyResult !== null ? (
              <motion.div key="verify" {...reveal}>
                {mode === "search" ? (
                  <RecognizeOrRaw data={verifyResult} />
                ) : (
                  <VerifyOrRaw data={verifyResult} />
                )}
              </motion.div>
            ) : null}
            {spoofed && padResult ? (
              <motion.div key="pad" {...reveal}>
                <PadResultPanel pad={padResult} />
              </motion.div>
            ) : null}
          </AnimatePresence>
        </aside>
      </div>
    </section>
  );
};

export default FaceLabPage;
