import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  ThemeProvider,
  createTheme,
  Button,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  Box,
  Stack,
} from "@mui/material";
import axios from "axios";
import axiosInstance, { getCookie } from "../api";
import { apiUrl } from "../../apiConfig";
import { installFaceLabAxiosLogging } from "../faceLab/faceLabAxiosLogging";

installFaceLabAxiosLogging(axiosInstance);
import Breadcrumbs from "../components/Breadcrumbs";
import LoaderComponent from "../components/LoaderComponent";
import FaceCameraOverlay from "../faceLab/camera/FaceCameraOverlay";
import type {
  CameraGuidanceContext,
  FaceCameraOverlayRef,
} from "../faceLab/camera/types";
import {
  parsePadResult,
  parseRecognizeResponse,
  parseVerifyPayload,
  type FaceVerifyApiResponse,
} from "../faceLab/faceLabApi";
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
  humanizeGallerySearchError,
  humanizePadFailureReason,
} from "../faceLab/faceLabHumanMessages";
import { FaceLabStaffCombobox } from "../faceLab/FaceLabStaffCombobox";
import type { StaffPickOption } from "../faceLab/FaceLabStaffCombobox";
import {
  FaceLabBootstrapPanel,
  type BootstrapAngle,
} from "../faceLab/FaceLabBootstrapPanel";
import { useMuiDarkSync } from "../faceLab/useMuiDarkSync";
import {
  readVoiceLang,
  persistVoiceLang,
  warmFaceLabTtsVoicePack,
  type FaceLabVoiceLang,
} from "../faceLab/faceLabCameraVoice";
import {
  FaCamera,
  FaCheckCircle,
  FaCircleNotch,
  FaExclamationTriangle,
  FaFolderOpen,
  FaImage,
  FaSearch,
  FaUserCheck,
  FaUserPlus,
  FaVolumeMute,
} from "react-icons/fa";

type LabMode = "search" | "compare" | "bootstrap";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(bytes < 10240 ? 1 : 0)} КБ`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

type FaceLabStaffOptionRow = {
  pin: string;
  fio: string;
  dept_id: number;
  dept_name: string;
  face_profile_state?: string;
};

function authBearerHeaders(): Record<string, string> {
  const t = getCookie("access_token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

const FACE_LAB_HEAVY_REQUEST_MS = 180_000;

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null;
}

type SessionOutcome = "idle" | "success" | "fail" | "partial";

type FaceLabEvaluateResult = {
  outcome: SessionOutcome;
  message: string;
  headline?: string;
};

type ProductUiState =
  | "idle"
  | "ready"
  | "searching"
  | "found"
  | "not_found"
  | "error"
  | "retry_needed";

type ProductTone = "neutral" | "info" | "success" | "warning" | "danger";

type StatusCardSpec = {
  state: ProductUiState;
  tone: ProductTone;
  badge: string;
  title: string;
  detail: string;
  nextStep?: string;
};

const DEFAULT_OUTCOME_HEADLINE: Record<
  Exclude<SessionOutcome, "idle">,
  string
> = {
  success: "Готово",
  partial: "Частичный результат",
  fail: "Пока без подтверждения",
};

function padTrustStrong(pad: PadTestResponse | null): boolean {
  return (
    pad !== null && (pad.decision === "YES" || pad.trust_confirmed === true)
  );
}

function padTrustWeak(pad: PadTestResponse | null): boolean {
  return pad !== null && pad.decision !== "YES" && pad.trust_confirmed !== true;
}

function padBlocksBeforeRecognition(pad: PadTestResponse | null): boolean {
  if (!pad) return false;
  if (pad.decision === "NO") return true;
  if (pad.decision === "REVIEW") return false;
  const status = pad.status.trim().toLowerCase();
  if (pad.trust_confirmed === false) return true;
  if (status === "suspicious" || status === "error") return true;
  return !["clean", "review", "insufficient_input_review"].includes(status);
}

function compareOutcomeFromContract(
  c: FaceVerifyApiResponse,
): FaceLabEvaluateResult {
  const summary = (c.summary || c.decision_summary || "").trim();
  if (c.matched && c.final_decision === "YES") {
    return {
      outcome: "success",
      headline: "Да",
      message: summary || "Совпадение есть.",
    };
  }
  return {
    outcome: "fail",
    headline: "Нет",
    message: summary || "Совпадения нет.",
  };
}

function personLabel(
  row:
    | {
        name?: string;
        surname?: string;
        fio?: string;
      }
    | null
    | undefined,
): string {
  if (!row) return "Сотрудник";
  if (typeof row.fio === "string" && row.fio.trim()) return row.fio.trim();
  const combined = [row.surname, row.name].filter(Boolean).join(" ").trim();
  return combined || "Сотрудник";
}

function bestRecognizedStaff(rec: ReturnType<typeof parseRecognizeResponse>) {
  if (!rec || rec.recognized_staff.length === 0) return null;
  return rec.recognized_staff.reduce((best, row) =>
    row.similarity > best.similarity ? row : best,
  );
}

function toneShellClass(tone: ProductTone): string {
  if (tone === "success") {
    return "border-emerald-200 bg-emerald-50/95 text-emerald-950 dark:border-emerald-800/50 dark:bg-emerald-950/35 dark:text-emerald-50";
  }
  if (tone === "info") {
    return "border-sky-200 bg-sky-50/95 text-sky-950 dark:border-sky-800/50 dark:bg-sky-950/35 dark:text-sky-50";
  }
  if (tone === "warning") {
    return "border-amber-200 bg-amber-50/95 text-amber-950 dark:border-amber-800/50 dark:bg-amber-950/35 dark:text-amber-50";
  }
  if (tone === "danger") {
    return "border-rose-200 bg-rose-50/95 text-rose-950 dark:border-rose-800/50 dark:bg-rose-950/35 dark:text-rose-50";
  }
  return "border-slate-200 bg-white/95 text-slate-950 dark:border-slate-700/70 dark:bg-slate-900/55 dark:text-slate-50";
}

function toneBadgeClass(tone: ProductTone): string {
  if (tone === "success") {
    return "border-emerald-200/80 bg-emerald-100/90 text-emerald-800 dark:border-emerald-700/40 dark:bg-emerald-500/15 dark:text-emerald-200";
  }
  if (tone === "info") {
    return "border-sky-200/80 bg-sky-100/90 text-sky-800 dark:border-sky-700/40 dark:bg-sky-500/15 dark:text-sky-200";
  }
  if (tone === "warning") {
    return "border-amber-200/80 bg-amber-100/90 text-amber-900 dark:border-amber-700/40 dark:bg-amber-500/15 dark:text-amber-100";
  }
  if (tone === "danger") {
    return "border-rose-200/80 bg-rose-100/90 text-rose-800 dark:border-rose-700/40 dark:bg-rose-500/15 dark:text-rose-200";
  }
  return "border-slate-200/80 bg-slate-100/90 text-slate-700 dark:border-slate-700/60 dark:bg-slate-800/90 dark:text-slate-200";
}

function PrimaryStateIcon({
  state,
  busy,
}: {
  state: ProductUiState;
  busy?: boolean;
}) {
  if (busy || state === "searching") {
    return <FaCircleNotch className="h-5 w-5 animate-spin" aria-hidden />;
  }
  if (state === "found") {
    return <FaCheckCircle className="h-5 w-5" aria-hidden />;
  }
  if (state === "error") {
    return <FaExclamationTriangle className="h-5 w-5" aria-hidden />;
  }
  if (state === "retry_needed") {
    return <FaCamera className="h-5 w-5" aria-hidden />;
  }
  if (state === "not_found") {
    return <FaSearch className="h-5 w-5" aria-hidden />;
  }
  return <FaUserCheck className="h-5 w-5" aria-hidden />;
}

function PrimaryStateCard({
  spec,
  busy,
}: {
  spec: StatusCardSpec;
  busy?: boolean;
}) {
  return (
    <motion.section
      className={`rounded-2xl border p-4 shadow-sm sm:p-5 ${toneShellClass(spec.tone)}`}
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 300, damping: 24 }}
      aria-live="polite"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border ${toneBadgeClass(spec.tone)}`}
          >
            <PrimaryStateIcon state={spec.state} busy={busy} />
          </span>
          <div className="min-w-0">
            <span
              className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase ${toneBadgeClass(spec.tone)}`}
            >
              {spec.badge}
            </span>
            <p className="mt-2 text-lg font-semibold leading-snug">
              {spec.title}
            </p>
            {spec.detail ? (
              <p className="mt-2 text-sm leading-relaxed opacity-90">
                {spec.detail}
              </p>
            ) : null}
            {spec.nextStep ? (
              <p className="mt-2 text-sm font-medium opacity-80">
                {spec.nextStep}
              </p>
            ) : null}
          </div>
        </div>
      </div>
    </motion.section>
  );
}

function ModeCard({
  active,
  title,
  detail,
  icon,
  onClick,
}: {
  active: boolean;
  title: string;
  detail?: string;
  icon: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`group rounded-xl border p-3 text-left transition-[background-color,border-color,box-shadow,transform] duration-150 hover:-translate-y-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/70 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-blue-300/70 dark:focus-visible:ring-offset-slate-950 ${
        active
          ? "border-blue-400 bg-blue-50 text-blue-950 shadow-sm shadow-blue-500/15 dark:border-blue-400/70 dark:bg-[#10254a] dark:text-blue-50 dark:shadow-blue-950/40"
          : "border-slate-200/90 bg-white/85 text-slate-900 hover:border-blue-300 hover:bg-blue-50/70 hover:shadow-sm hover:shadow-blue-500/10 dark:border-slate-700/70 dark:bg-slate-900/55 dark:text-slate-100 dark:hover:border-blue-500/60 dark:hover:bg-blue-500/10 dark:hover:shadow-blue-950/30"
      }`}
    >
      <div className="flex items-start gap-3">
        <span
          className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors ${
            active
              ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20 dark:bg-blue-500"
              : "bg-slate-100 text-slate-600 group-hover:bg-blue-100 group-hover:text-blue-700 dark:bg-slate-800 dark:text-slate-300 dark:group-hover:bg-blue-500/15 dark:group-hover:text-blue-200"
          }`}
        >
          {icon}
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold">{title}</p>
          {detail ? (
            <p
              className={`mt-0.5 text-xs leading-relaxed ${
                active
                  ? "text-blue-900/75 dark:text-blue-100/75"
                  : "text-slate-600 group-hover:text-slate-700 dark:text-slate-400 dark:group-hover:text-slate-300"
              }`}
            >
              {detail}
            </p>
          ) : null}
        </div>
      </div>
    </button>
  );
}

function evaluateFaceLabSession(
  mode: LabMode,
  pad: PadTestResponse | null,
  padWarning: string | null,
  verifyPayload: unknown,
): FaceLabEvaluateResult {
  if (mode === "compare") {
    if (padWarning) {
      const f = humanizePadFailureReason(padWarning);
      return {
        outcome: "fail",
        message: [f.title, f.detail].filter(Boolean).join(" "),
        headline: "Проверка фото не пройдена",
      };
    }
    const parsed = parseVerifyPayload(verifyPayload);
    if (!parsed) {
      const errRaw =
        isRecord(verifyPayload) && typeof verifyPayload.error === "string"
          ? verifyPayload.error
          : "Не удалось разобрать ответ сервера.";
      const f = humanizeApiError(errRaw);
      return {
        outcome: "fail",
        message: [f.title, f.detail].filter(Boolean).join(" "),
      };
    }
    if (!parsed.liveness.checked) {
      return {
        outcome: "fail",
        message: "Проверка фото не пришла.",
      };
    }
    return compareOutcomeFromContract(parsed);
  }

  if (padWarning) {
    const f = humanizePadFailureReason(padWarning);
    return {
      outcome: "fail",
      message: [f.title, f.detail].filter(Boolean).join(" "),
      headline: "Проверка фото не пройдена",
    };
  }

  if (pad === null) {
    return {
      outcome: "fail",
      message: "Проверка не завершилась. Снимите ещё раз.",
      headline: "Повторите",
    };
  }

  if (padBlocksBeforeRecognition(pad)) {
    return {
      outcome: "fail",
      message: "Фото не принято. Снимите ещё раз.",
      headline: "Новый кадр",
    };
  }

  const padStrong = padTrustStrong(pad);
  const padWeak = padTrustWeak(pad);

  const rec = parseRecognizeResponse(verifyPayload);
  if (!rec) {
    const errRaw =
      isRecord(verifyPayload) && typeof verifyPayload.error === "string"
        ? verifyPayload.error
        : "";
    if (errRaw) {
      const g = humanizeGallerySearchError(errRaw);
      return {
        outcome: g.outcome,
        message: [g.title, g.detail].filter(Boolean).join(" "),
        headline: g.headline,
      };
    }
    const f = humanizeApiError("Не удалось разобрать ответ сервера.");
    return {
      outcome: "fail",
      message: [f.title, f.detail].filter(Boolean).join(" "),
      headline: "Ответ сервера неполный",
    };
  }

  const hits = rec.recognized_staff.length > 0;
  const unknownN = rec.unknown_faces.length;

  if (hits && padStrong) {
    return {
      outcome: "success",
      message: `Найдено: ${rec.recognized_staff.length}. Фото принято.`,
    };
  }

  if (hits && padWeak) {
    return {
      outcome: "partial",
      message: "Совпадение есть, но фото слабое.",
      headline: "Лучше переснять",
    };
  }

  if (!hits && padStrong) {
    return {
      outcome: "partial",
      message:
        unknownN > 0
          ? "Фото принято, но совпадения нет."
          : "Фото принято, совпадения нет.",
      headline: "Не нашли",
    };
  }

  return {
    outcome: "partial",
    message: "Совпадения нет. Снимите ещё раз.",
    headline: "Переснимите",
  };
}

const FaceLabPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const urlBootstrapAppliedRef = useRef(false);
  const [mode, setMode] = useState<LabMode>("search");
  const [allStaffFlat, setAllStaffFlat] = useState<StaffPickOption[]>([]);
  const [allStaffLoading, setAllStaffLoading] = useState(false);
  const [staffListError, setStaffListError] = useState<string | null>(null);
  const [staffSearchFocusTick, setStaffSearchFocusTick] = useState(0);
  const [selectedPin, setSelectedPin] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [padResult, setPadResult] = useState<PadTestResponse | null>(null);
  const [padWarning, setPadWarning] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionOutcome, setSessionOutcome] = useState<SessionOutcome>("idle");
  const [outcomeMessage, setOutcomeMessage] = useState("");
  const [outcomeHeadline, setOutcomeHeadline] = useState<string | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const cameraRef = useRef<FaceCameraOverlayRef>(null);
  const [cameraBootstrapAngle, setCameraBootstrapAngle] =
    useState<BootstrapAngle | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileConsentDone, setFileConsentDone] = useState(readFileConsent);
  const [fileConsentOpen, setFileConsentOpen] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const muiDark = useMuiDarkSync();
  const muiTheme = useMemo(
    () =>
      createTheme({
        palette: {
          mode: muiDark ? "dark" : "light",
          primary: { main: "#2563eb" },
          secondary: { main: "#7c3aed" },
        },
        shape: { borderRadius: 12 },
        typography: { fontFamily: '"Inter", "system-ui", "sans-serif"' },
      }),
    [muiDark],
  );
  const [voiceLang, setVoiceLang] = useState<FaceLabVoiceLang>(() =>
    readVoiceLang(),
  );

  useEffect(() => {
    persistVoiceLang(voiceLang);
  }, [voiceLang]);

  useEffect(() => {
    if (voiceLang === "off") return;
    void warmFaceLabTtsVoicePack(voiceLang);
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
    if (mode !== "bootstrap") {
      setCameraBootstrapAngle(null);
    }
  }, [mode]);

  const cameraGuidanceContext = useMemo((): CameraGuidanceContext => {
    if (mode === "search" || mode === "compare") return "profile_photo";
    if (mode !== "bootstrap") return "default";
    if (cameraBootstrapAngle === "front") return "bootstrap_front";
    if (cameraBootstrapAngle === "left") return "bootstrap_left";
    if (cameraBootstrapAngle === "right") return "bootstrap_right";
    return "default";
  }, [mode, cameraBootstrapAngle]);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [file]);

  const onCameraShot = useCallback((blob: Blob) => {
    const f = new File([blob], "face-lab-capture.jpg", {
      type: blob.type || "image/jpeg",
    });
    setFile(f);
    setSessionOutcome("idle");
    setOutcomeMessage("");
    setOutcomeHeadline(null);
    setPadResult(null);
    setPadWarning(null);
    setVerifyResult(null);
  }, []);

  useEffect(() => {
    if (mode !== "compare" && mode !== "bootstrap") {
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
        const rows = Array.isArray(res.data) ? res.data : [];
        const byPin = new Map<string, StaffPickOption>();
        for (const row of rows) {
          const pin = String(row.pin ?? "").trim();
          if (!pin || byPin.has(pin)) continue;
          const fps =
            typeof row.face_profile_state === "string"
              ? row.face_profile_state.trim()
              : undefined;
          byPin.set(pin, {
            pin,
            fio: (row.fio ?? "").trim() || "Без ФИО",
            deptName: (row.dept_name ?? "").trim() || "Отдел",
            deptId: row.dept_id,
            faceProfileState: fps || undefined,
          });
        }
        const flat = Array.from(byPin.values()).sort((a, b) => {
          const c = a.fio.localeCompare(b.fio, "ru");
          return c !== 0 ? c : a.deptName.localeCompare(b.deptName, "ru");
        });
        setAllStaffFlat(flat);
        if (flat.length > 0) {
          setStaffSearchFocusTick((t) => t + 1);
        }
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
    setPadResult(null);
    setPadWarning(null);
    setVerifyResult(null);
    setSessionOutcome("idle");
    setOutcomeMessage("");
    setOutcomeHeadline(null);
    setError(null);
    cameraRef.current?.resetSession();
  }, []);

  const resetSessionFromScratch = useCallback(() => {
    setSessionOutcome("idle");
    setOutcomeMessage("");
    setOutcomeHeadline(null);
    setPadResult(null);
    setPadWarning(null);
    setVerifyResult(null);
    setError(null);
    setFile(null);
    setFileInputKey((k) => k + 1);
    setSelectedPin("");
    cameraRef.current?.resetSession();
  }, []);

  const requestOpenCamera = useCallback(() => {
    void cameraRef.current?.open("user");
  }, []);

  const requestPickFile = useCallback(() => {
    if (!fileConsentDone) {
      setFileConsentOpen(true);
      return;
    }
    fileInputRef.current?.click();
  }, [fileConsentDone]);

  const confirmFileConsent = useCallback(() => {
    persistFileConsent();
    setFileConsentDone(true);
    setFileConsentOpen(false);
    setTimeout(() => fileInputRef.current?.click(), 0);
  }, []);

  const onSubmit = async () => {
    setError(null);
    setPadWarning(null);
    setPadResult(null);
    setVerifyResult(null);
    setSessionOutcome("idle");
    setOutcomeMessage("");
    setOutcomeHeadline(null);
    if (!file) {
      setError("Сначала снимите фото камерой или выберите файл на устройстве.");
      return;
    }
    if (mode === "bootstrap") {
      setError("В настройке входа сохраните кадр кнопкой под превью.");
      return;
    }
    if (mode === "compare" && !selectedPin) {
      setError("В режиме «С эталоном» нужно выбрать сотрудника в поле поиска.");
      return;
    }
    setBusy(true);

    let padLocal: PadTestResponse | null = null;
    let padWarnLocal: string | null = null;
    let verifyLocal: unknown = null;

    try {
      setPadResult(null);
      setPadWarning(null);

      const headers = authBearerHeaders();

      if (mode === "search") {
        const padFd = new FormData();
        padFd.append("image", file);
        const padRes = await axiosInstance.post("face-lab/pad-test/", padFd, {
          timeout: FACE_LAB_HEAVY_REQUEST_MS,
        });
        padLocal = parsePadResult(padRes.data);
        if (padLocal) {
          setPadResult(padLocal);
        } else {
          padWarnLocal = "Не удалось разобрать результат проверки фото.";
          setPadWarning(padWarnLocal);
        }

        if (padLocal && !padBlocksBeforeRecognition(padLocal)) {
          const fd = new FormData();
          fd.append("image", file);
          const res = await axios.post(`${apiUrl}/recognize-faces/`, fd, {
            headers,
            timeout: FACE_LAB_HEAVY_REQUEST_MS,
          });
          verifyLocal = res.data;
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
        verifyLocal = res.data;
        setVerifyResult(res.data);
      }

      const ev = evaluateFaceLabSession(
        mode,
        padLocal,
        padWarnLocal,
        verifyLocal,
      );
      setSessionOutcome(ev.outcome);
      setOutcomeMessage(ev.message);
      setOutcomeHeadline(ev.headline ?? null);
    } catch (err: unknown) {
      if (
        axios.isAxiosError(err) &&
        err.response?.data &&
        isRecord(err.response.data)
      ) {
        verifyLocal = err.response.data;
        setVerifyResult(err.response.data);
        setError(null);
      } else {
        setVerifyResult(null);
        setError(err instanceof Error ? err.message : "Запрос не удался.");
      }
      const ev = evaluateFaceLabSession(
        mode,
        padLocal,
        padWarnLocal,
        verifyLocal,
      );
      setSessionOutcome(ev.outcome);
      setOutcomeMessage(ev.message);
      setOutcomeHeadline(ev.headline ?? null);
    } finally {
      setBusy(false);
    }
  };

  const errorFriendly = error ? humanizeApiError(error) : null;
  const staffListErrorFriendly = staffListError
    ? humanizeApiError(staffListError)
    : null;
  const padWarningFriendly = padWarning
    ? humanizePadFailureReason(padWarning)
    : null;
  const selectedStaff = useMemo(
    () => allStaffFlat.find((row) => row.pin === selectedPin) ?? null,
    [allStaffFlat, selectedPin],
  );
  const recognized = useMemo(
    () => (mode === "search" ? parseRecognizeResponse(verifyResult) : null),
    [mode, verifyResult],
  );
  const verifyContract = useMemo(
    () => (mode === "compare" ? parseVerifyPayload(verifyResult) : null),
    [mode, verifyResult],
  );
  const verifyPayloadError =
    isRecord(verifyResult) && typeof verifyResult.error === "string"
      ? verifyResult.error
      : null;
  const primaryStateSpec = useMemo<StatusCardSpec>(() => {
    const fallbackHeadline =
      sessionOutcome !== "idle"
        ? (outcomeHeadline ?? DEFAULT_OUTCOME_HEADLINE[sessionOutcome])
        : null;
    const fallbackMessage = outcomeMessage.trim();
    const selectedName = selectedStaff?.fio?.trim() || "Сотрудник";

    if (mode === "search") {
      if (busy) {
        return {
          state: "searching",
          tone: "info",
          badge: "Идёт поиск",
          title: "Ищем человека в базе",
          detail: "Сравниваем фото с базой.",
        };
      }
      if (!file) {
        return {
          state: "idle",
          tone: "neutral",
          badge: "Готово к поиску",
          title: "Сначала нужен кадр",
          detail: "Сделайте снимок или загрузите фото.",
          nextStep: "Лицо по центру, свет ровный.",
        };
      }
      if (recognized) {
        const best = bestRecognizedStaff(recognized);
        if (best) {
          const padAction = padResult?.diagnostics?.decision?.operator_action;
          const padNeedsHuman =
            Boolean(padWarning) ||
            padResult?.trust_confirmed === false ||
            padAction === "manual_review" ||
            padAction === "retry_photo" ||
            padAction === "reject";
          const padCaution =
            !padNeedsHuman &&
            (padAction === "accept_with_caution" || padTrustWeak(padResult));
          return {
            state: "found",
            tone: padNeedsHuman ? "warning" : "success",
            badge: padNeedsHuman ? "Найдено, нужен новый кадр" : "Найдено",
            title: personLabel(best),
            detail: padNeedsHuman
              ? `Кандидат ${Math.round(best.similarity * 100)}%. Лучше переснять.`
              : padCaution
                ? `Кандидат ${Math.round(best.similarity * 100)}%. Фото принято.`
                : `Кандидат ${Math.round(best.similarity * 100)}%.`,
            nextStep: padNeedsHuman
              ? "Лицо ближе, без бликов."
              : padCaution
                ? "Можно продолжать."
                : "Можно продолжать.",
          };
        }
        const retryNeeded = Boolean(padWarning) || padTrustWeak(padResult);
        return {
          state: retryNeeded ? "retry_needed" : "not_found",
          tone: "warning",
          badge: retryNeeded ? "Нужен новый кадр" : "Не найдено",
          title: retryNeeded
            ? "Надёжного совпадения нет"
            : "Поиск никого не подтвердил",
          detail: retryNeeded
            ? "Кадр слабый или сходство ниже порога."
            : "Совпадения в базе нет.",
          nextStep: "Снимите ближе и ровнее.",
        };
      }
      if (verifyPayloadError) {
        const help = humanizeGallerySearchError(verifyPayloadError);
        return {
          state: help.outcome === "fail" ? "retry_needed" : "error",
          tone: help.outcome === "fail" ? "warning" : "danger",
          badge: help.outcome === "fail" ? "Нужен новый кадр" : "Ошибка",
          title: help.headline,
          detail: [help.title, help.detail].filter(Boolean).join(". "),
          nextStep:
            help.outcome === "fail"
              ? "Сделайте новый кадр."
              : "Повторите позже.",
        };
      }
      if (errorFriendly) {
        return {
          state: "error",
          tone: "danger",
          badge: "Ошибка",
          title: errorFriendly.title,
          detail: errorFriendly.detail ?? "Поиск не завершился.",
          nextStep: "Повторите попытку.",
        };
      }
      if (fallbackHeadline || fallbackMessage) {
        return {
          state:
            sessionOutcome === "success"
              ? "found"
              : sessionOutcome === "partial"
                ? "retry_needed"
                : "error",
          tone:
            sessionOutcome === "success"
              ? "success"
              : sessionOutcome === "partial"
                ? "warning"
                : "danger",
          badge:
            sessionOutcome === "success"
              ? "Найдено"
              : sessionOutcome === "partial"
                ? "Нужен новый кадр"
                : "Ошибка",
          title: fallbackHeadline ?? "Итог готов",
          detail: fallbackMessage || "Результат поиска готов.",
        };
      }
      return {
        state: "ready",
        tone: "info",
        badge: "Кадр готов",
        title: "Можно запускать поиск",
        detail: "Фото выбрано.",
        nextStep: "Запустите поиск.",
      };
    }

    if (mode === "compare") {
      if (busy) {
        return {
          state: "searching",
          tone: "info",
          badge: "Идёт сверка",
          title: "Сверяем лицо с эталоном",
          detail: "Проверяем совпадение.",
        };
      }
      if (!selectedPin) {
        return {
          state: "idle",
          tone: "neutral",
          badge: "Нужен выбор",
          title: "Сначала выберите сотрудника",
          detail: "Выберите человека для сверки.",
          nextStep: "Введите ФИО, PIN или отдел.",
        };
      }
      if (!file) {
        return {
          state: "ready",
          tone: "info",
          badge: "Ждём кадр",
          title: `Выбран: ${selectedName}`,
          detail: "Теперь нужен снимок.",
          nextStep: "Откройте камеру или загрузите фото.",
        };
      }
      if (verifyContract) {
        const matched =
          verifyContract.matched && verifyContract.final_decision === "YES";
        const contractSummary = (
          verifyContract.summary ||
          verifyContract.decision_summary ||
          ""
        ).trim();
        if (matched) {
          return {
            state: "found",
            tone: "success",
            badge: "Подтверждено",
            title: `${selectedName}: да`,
            detail: contractSummary || "Совпадение есть.",
            nextStep: "Можно продолжать.",
          };
        }
        if (
          verifyContract.status === "QUALITY_FAIL" ||
          verifyContract.status === "PAD_ERROR" ||
          verifyContract.liveness.status === "insufficient_input_review"
        ) {
          return {
            state: "retry_needed",
            tone: "warning",
            badge: "Нужен новый кадр",
            title: "Кадр слабый",
            detail: contractSummary || "Нужен новый снимок.",
            nextStep: "Лицо ближе, свет ровный.",
          };
        }
        if (verifyContract.status === "LIVENESS_FAIL") {
          return {
            state: "error",
            tone: "danger",
            badge: "Кадр отклонён",
            title: "Фото не принято",
            detail: contractSummary || "Снимите ещё раз.",
            nextStep: "Лицо должно быть в рамке.",
          };
        }
        return {
          state: "not_found",
          tone: "danger",
          badge: "Не подтверждено",
          title: `${selectedName}: нет`,
          detail: contractSummary || "Совпадения нет.",
          nextStep: "При необходимости снимите ещё раз.",
        };
      }
      if (verifyPayloadError) {
        const help = humanizeApiError(verifyPayloadError);
        return {
          state: "error",
          tone: "danger",
          badge: "Ошибка",
          title: help.title,
          detail: help.detail ?? "Сверка не завершилась.",
          nextStep: "Повторите попытку.",
        };
      }
      if (errorFriendly) {
        return {
          state: "error",
          tone: "danger",
          badge: "Ошибка",
          title: errorFriendly.title,
          detail: errorFriendly.detail ?? "Сверка не завершилась.",
          nextStep: "Повторите попытку позже.",
        };
      }
      if (fallbackHeadline || fallbackMessage) {
        return {
          state:
            sessionOutcome === "success"
              ? "found"
              : sessionOutcome === "partial"
                ? "retry_needed"
                : "error",
          tone:
            sessionOutcome === "success"
              ? "success"
              : sessionOutcome === "partial"
                ? "warning"
                : "danger",
          badge:
            sessionOutcome === "success"
              ? "Подтверждено"
              : sessionOutcome === "partial"
                ? "Нужен новый кадр"
                : "Ошибка",
          title: fallbackHeadline ?? "Итог готов",
          detail: fallbackMessage || "Результат сверки готов.",
        };
      }
      return {
        state: "ready",
        tone: "info",
        badge: "Всё готово",
        title: `Можно сверять с профилем ${selectedName}`,
        detail: "Сотрудник и фото выбраны.",
        nextStep: "Нажмите «Сверить».",
      };
    }

    if (!selectedPin) {
      return {
        state: "idle",
        tone: "neutral",
        badge: "Шаг 1",
        title: "Сначала выберите сотрудника",
        detail: "Потом снимем три ракурса.",
        nextStep: "Начните с прямого кадра.",
      };
    }
    if (file) {
      return {
        state: "ready",
        tone: "success",
        badge: "Снимок готов",
        title: "Кадр уже можно сохранить",
        detail: "Сохраните этот ракурс.",
        nextStep: "Потом перейдите дальше.",
      };
    }
    return {
      state: "ready",
      tone: "info",
      badge: cameraBootstrapAngle ? "Текущий шаг" : "Подготовка",
      title:
        cameraBootstrapAngle === "left"
          ? "Снимите левый ракурс"
          : cameraBootstrapAngle === "right"
            ? "Снимите правый ракурс"
            : "Снимите прямой кадр",
      detail: "Сделайте один чёткий кадр.",
      nextStep: "Откройте камеру или загрузите фото.",
    };
  }, [
    mode,
    busy,
    file,
    recognized,
    padWarning,
    padResult,
    verifyPayloadError,
    errorFriendly,
    sessionOutcome,
    outcomeHeadline,
    outcomeMessage,
    selectedPin,
    selectedStaff,
    verifyContract,
    cameraBootstrapAngle,
  ]);

  const springLayoutMain = {
    type: "spring" as const,
    stiffness: 260,
    damping: 21,
    mass: 0.92,
  };

  return (
    <ThemeProvider theme={muiTheme}>
      <div className="mx-auto w-full max-w-[92rem] px-3 py-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] text-slate-900 dark:text-slate-100 sm:px-5 sm:py-6 md:px-8 lg:px-10">
        <header className="mb-5 rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm shadow-slate-200/40 backdrop-blur dark:border-slate-700/70 dark:bg-slate-950/55 dark:shadow-black/20 sm:p-5">
          <Breadcrumbs items={[{ label: "Face Lab", path: undefined }]} />
          <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold tracking-normal sm:text-3xl">
                Face Lab
              </h1>
              <p className="mt-1 max-w-2xl text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                Проверка живости, поиск по базе и сверка с эталоном в одном
                рабочем экране.
              </p>
            </div>
          </div>
        </header>

        <FaceCameraOverlay
          ref={cameraRef}
          onShot={onCameraShot}
          requireLiveness={mode !== "bootstrap"}
          voiceLang={voiceLang}
          guidanceContext={cameraGuidanceContext}
        />

        <FaceLabConsentDialog
          open={fileConsentOpen}
          title="Выбор файла"
          onCancel={() => setFileConsentOpen(false)}
          onConfirm={() => confirmFileConsent()}
          confirmLabel="Продолжить"
        >
          <p>
            Файл отправится только после того, как вы нажмёте «Отправить на
            проверку».
          </p>
        </FaceLabConsentDialog>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-12 lg:gap-6 lg:items-start">
          <motion.div
            layout
            transition={springLayoutMain}
            className="min-w-0 space-y-5 lg:col-span-5 xl:col-span-4"
          >
            <motion.div
              layout
              transition={springLayoutMain}
              className="w-full space-y-5"
            >
              <section className="rounded-2xl border border-slate-200/90 bg-white/95 p-4 shadow-sm shadow-slate-200/30 dark:border-slate-700/80 dark:bg-slate-950/55 dark:shadow-black/25 sm:p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="text-xs font-semibold uppercase text-slate-500">
                      Режим
                    </h2>
                    <p className="mt-1 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                      Что делаем с новым кадром.
                    </p>
                  </div>
                </div>

                <div className="mt-4 grid gap-2.5">
                  <ModeCard
                    active={mode === "search"}
                    title="Поиск по базе"
                    detail="Проверка кадра, затем совпадения в галерее."
                    icon={<FaSearch className="h-4 w-4" aria-hidden />}
                    onClick={() => {
                      setMode("search");
                      setError(null);
                      resetSessionFromScratch();
                    }}
                  />
                  <ModeCard
                    active={mode === "compare"}
                    title="Сверка с эталоном"
                    detail="Выбор сотрудника и сравнение с профилем."
                    icon={<FaUserCheck className="h-4 w-4" aria-hidden />}
                    onClick={() => {
                      setMode("compare");
                      setError(null);
                      resetSessionFromScratch();
                    }}
                  />
                  <ModeCard
                    active={mode === "bootstrap"}
                    title="Настройка входа"
                    detail="Три ракурса для будущего входа."
                    icon={<FaUserPlus className="h-4 w-4" aria-hidden />}
                    onClick={() => {
                      setMode("bootstrap");
                      setError(null);
                      resetSessionFromScratch();
                    }}
                  />
                </div>
              </section>

              {(mode === "compare" || mode === "bootstrap") && (
                <section
                  className={`rounded-2xl border border-slate-200/90 bg-white/95 p-4 shadow-sm shadow-slate-200/30 dark:border-slate-700/80 dark:bg-slate-950/55 dark:shadow-black/25 sm:p-5 ${
                    mode === "bootstrap"
                      ? "ring-1 ring-blue-500/15 dark:ring-blue-400/20"
                      : ""
                  }`}
                >
                  {mode === "bootstrap" ? (
                    <div className="mb-5 border-b border-slate-200/80 pb-4 dark:border-slate-600/60">
                      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-50">
                        Настройка входа по лицу
                      </h2>
                      <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                        Выберите человека и сохраните три ракурса.
                      </p>
                    </div>
                  ) : (
                    <div className="mb-4">
                      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-50">
                        Сверка с выбранным сотрудником
                      </h2>
                      <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                        Выберите сотрудника, затем сделайте новый кадр для
                        сравнения.
                      </p>
                    </div>
                  )}
                  {staffListError ? (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-800/40 dark:bg-amber-950/20 dark:text-amber-100">
                      <p className="font-medium">
                        {staffListErrorFriendly?.title ?? staffListError}
                      </p>
                      {staffListErrorFriendly?.detail ? (
                        <p className="mt-1 text-amber-900/90 dark:text-amber-200/90">
                          {staffListErrorFriendly.detail}
                        </p>
                      ) : null}
                    </div>
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
                    <p className="text-sm text-slate-600 dark:text-slate-500">
                      Нет ни одного сотрудника с привязкой к отделу. Проверьте
                      права или настройки.
                    </p>
                  ) : (
                    <FaceLabStaffCombobox
                      options={allStaffFlat}
                      value={selectedPin}
                      onChange={setSelectedPin}
                      focusRequestId={staffSearchFocusTick}
                      label={
                        mode === "bootstrap"
                          ? "Кого настраиваем"
                          : "Кого сверяем"
                      }
                      emptyResultText="Ничего не нашли. Попробуйте ФИО, PIN или отдел."
                    />
                  )}
                </section>
              )}

              <motion.section
                layout
                transition={springLayoutMain}
                className="rounded-2xl border border-slate-200/90 bg-white/95 p-4 shadow-sm shadow-slate-200/30 dark:border-slate-700/80 dark:bg-slate-950/55 dark:shadow-black/25 sm:p-5"
              >
                <Stack
                  direction={{ xs: "column", sm: "row" }}
                  spacing={1.5}
                  alignItems={{ sm: "center" }}
                  justifyContent="space-between"
                  className="mb-5"
                >
                  <div>
                    <h2 className="text-xs font-semibold uppercase text-slate-500">
                      {mode === "bootstrap"
                        ? "Кадр текущего шага"
                        : mode === "search"
                          ? "Кадр для поиска"
                          : "Кадр для сравнения"}
                    </h2>
                  </div>
                  <ToggleButtonGroup
                    exclusive
                    size="small"
                    value={voiceLang}
                    onChange={(_, v: FaceLabVoiceLang | null) => {
                      if (v != null) setVoiceLang(v);
                    }}
                    aria-label={
                      mode === "bootstrap"
                        ? "Голосовые подсказки для шагов настройки"
                        : "Озвучка подсказок камеры"
                    }
                    sx={(theme) => ({
                      flexWrap: "wrap",
                      gap: 0.5,
                      justifyContent: { xs: "flex-start", sm: "flex-end" },
                      "& .MuiToggleButton-root": {
                        px: 1.25,
                        py: 0.65,
                        textTransform: "none",
                        fontWeight: 600,
                        borderRadius: "10px",
                        border: "1px solid",
                        borderColor:
                          theme.palette.mode === "dark"
                            ? "rgba(148, 163, 184, 0.38)"
                            : "rgba(148, 163, 184, 0.55)",
                        color:
                          theme.palette.mode === "dark"
                            ? "rgb(203, 213, 225)"
                            : "rgb(51, 65, 85)",
                        backgroundColor:
                          theme.palette.mode === "dark"
                            ? "rgba(15, 23, 42, 0.62)"
                            : "rgba(255, 255, 255, 0.82)",
                        transition:
                          "background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease, box-shadow 0.15s ease",
                        "&:hover": {
                          borderColor:
                            theme.palette.mode === "dark"
                              ? "rgba(96, 165, 250, 0.7)"
                              : "rgba(37, 99, 235, 0.55)",
                          backgroundColor:
                            theme.palette.mode === "dark"
                              ? "rgba(37, 99, 235, 0.18)"
                              : "rgba(239, 246, 255, 0.95)",
                          color:
                            theme.palette.mode === "dark"
                              ? "rgb(219, 234, 254)"
                              : "rgb(30, 64, 175)",
                        },
                        "&.Mui-selected": {
                          backgroundColor:
                            theme.palette.mode === "dark"
                              ? "rgb(59, 130, 246)"
                              : "rgb(37, 99, 235)",
                          color: "#fff",
                          borderColor:
                            theme.palette.mode === "dark"
                              ? "rgb(147, 197, 253)"
                              : "rgb(37, 99, 235)",
                          boxShadow:
                            theme.palette.mode === "dark"
                              ? "0 0 0 1px rgba(191,219,254,0.22), 0 6px 18px rgba(30,64,175,0.35)"
                              : "0 0 0 1px rgba(37,99,235,0.16), 0 6px 18px rgba(37,99,235,0.22)",
                          "&:hover": {
                            backgroundColor:
                              theme.palette.mode === "dark"
                                ? "rgb(37, 99, 235)"
                                : "rgb(29, 78, 216)",
                          },
                        },
                      },
                    })}
                  >
                    <ToggleButton value="off" aria-label="Без звука">
                      <FaVolumeMute className="h-3.5 w-3.5" />
                    </ToggleButton>
                    <ToggleButton value="ru">RU</ToggleButton>
                    <ToggleButton value="kk">KZ</ToggleButton>
                    <ToggleButton value="en">EN</ToggleButton>
                  </ToggleButtonGroup>
                </Stack>
                <Stack
                  direction={{ xs: "column", sm: "row" }}
                  spacing={2.5}
                  className="w-full"
                  sx={{ alignItems: "stretch" }}
                >
                  <Button
                    variant="outlined"
                    size="large"
                    startIcon={<FaCamera />}
                    onClick={() => requestOpenCamera()}
                    fullWidth
                    sx={(theme) => ({
                      minHeight: 52,
                      py: 1.35,
                      px: 2,
                      flex: { sm: 1 },
                      borderRadius: 2,
                      borderWidth: 1.5,
                      textTransform: "none",
                      fontWeight: 600,
                      fontSize: "0.95rem",
                      color:
                        theme.palette.mode === "dark"
                          ? "rgb(147, 197, 253)"
                          : "rgb(37, 99, 235)",
                      borderColor:
                        theme.palette.mode === "dark"
                          ? "rgba(96, 165, 250, 0.55)"
                          : "rgba(37, 99, 235, 0.62)",
                      backgroundColor:
                        theme.palette.mode === "dark"
                          ? "rgba(37, 99, 235, 0.08)"
                          : "rgba(239, 246, 255, 0.45)",
                      transition:
                        "transform 0.12s ease, box-shadow 0.12s ease, border-color 0.12s ease",
                      "&:hover": {
                        borderColor:
                          theme.palette.mode === "dark"
                            ? "rgb(147, 197, 253)"
                            : "rgb(29, 78, 216)",
                        backgroundColor:
                          theme.palette.mode === "dark"
                            ? "rgba(37, 99, 235, 0.18)"
                            : "rgba(219, 234, 254, 0.9)",
                        boxShadow:
                          theme.palette.mode === "dark"
                            ? "0 2px 16px rgba(37, 99, 235, 0.28)"
                            : "0 2px 14px rgba(37, 99, 235, 0.16)",
                        transform: "translateY(-1px)",
                      },
                    })}
                  >
                    Снять камерой
                  </Button>
                  <input
                    ref={fileInputRef}
                    key={fileInputKey}
                    type="file"
                    accept="image/png,image/jpeg,.png,.jpg,.jpeg,.PNG,.JPG,.JPEG"
                    className="sr-only"
                    tabIndex={-1}
                    aria-label="Выбор файла изображения для проверки"
                    onChange={(e) => {
                      const f = e.target.files?.[0] ?? null;
                      setFile(f);
                      if (f) {
                        setSessionOutcome("idle");
                        setOutcomeMessage("");
                        setOutcomeHeadline(null);
                        setPadResult(null);
                        setPadWarning(null);
                        setVerifyResult(null);
                      }
                    }}
                  />
                  <Button
                    variant="outlined"
                    size="large"
                    startIcon={<FaFolderOpen />}
                    onClick={() => requestPickFile()}
                    fullWidth
                    sx={(theme) => ({
                      minHeight: 52,
                      py: 1.35,
                      px: 2,
                      flex: { sm: 1 },
                      borderRadius: 2,
                      borderWidth: 1.5,
                      textTransform: "none",
                      fontWeight: 600,
                      fontSize: "0.95rem",
                      color:
                        theme.palette.mode === "dark"
                          ? "rgb(147, 197, 253)"
                          : "rgb(37, 99, 235)",
                      borderColor:
                        theme.palette.mode === "dark"
                          ? "rgba(96, 165, 250, 0.55)"
                          : "rgba(37, 99, 235, 0.62)",
                      backgroundColor:
                        theme.palette.mode === "dark"
                          ? "rgba(37, 99, 235, 0.08)"
                          : "rgba(239, 246, 255, 0.45)",
                      transition:
                        "transform 0.12s ease, box-shadow 0.12s ease, border-color 0.12s ease",
                      "&:hover": {
                        borderColor:
                          theme.palette.mode === "dark"
                            ? "rgb(147, 197, 253)"
                            : "rgb(29, 78, 216)",
                        backgroundColor:
                          theme.palette.mode === "dark"
                            ? "rgba(37, 99, 235, 0.18)"
                            : "rgba(219, 234, 254, 0.9)",
                        boxShadow:
                          theme.palette.mode === "dark"
                            ? "0 2px 16px rgba(37, 99, 235, 0.28)"
                            : "0 2px 14px rgba(37, 99, 235, 0.16)",
                        transform: "translateY(-1px)",
                      },
                    })}
                  >
                    Загрузить фото
                  </Button>
                </Stack>

                {previewUrl ? (
                  <Box className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-600 dark:bg-slate-950/80 md:p-5">
                    <Stack
                      direction="row"
                      alignItems="center"
                      gap={1}
                      className="mb-3 text-slate-500 dark:text-slate-400"
                    >
                      <FaImage className="h-4 w-4" aria-hidden />
                      <Typography
                        variant="caption"
                        fontWeight={600}
                        letterSpacing={0}
                        textTransform="uppercase"
                      >
                        Превью
                      </Typography>
                    </Stack>
                    <Box className="flex flex-col items-center gap-4 md:mx-auto md:max-w-3xl">
                      <img
                        src={previewUrl}
                        alt="Кадр для проверки"
                        className="h-auto w-full max-h-[min(42vh,320px)] rounded-xl border border-slate-200 bg-black/30 object-contain shadow-inner dark:border-slate-600 md:max-h-[min(52vh,420px)]"
                      />
                      <Stack
                        direction="row"
                        alignItems="center"
                        gap={1.5}
                        className="w-full justify-center rounded-lg border border-slate-200/90 bg-white/80 px-4 py-3 dark:border-slate-600 dark:bg-slate-900/50"
                      >
                        <FaImage
                          className="h-4 w-4 shrink-0 text-blue-600 dark:text-blue-300"
                          aria-hidden
                        />
                        <div className="min-w-0 text-center">
                          <Typography
                            variant="body2"
                            fontWeight={600}
                            className="truncate text-slate-900 dark:text-slate-100"
                          >
                            {file?.name ?? "файл"}
                          </Typography>
                          {file ? (
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              className="block"
                            >
                              {formatFileSize(file.size)}
                            </Typography>
                          ) : null}
                        </div>
                      </Stack>
                    </Box>
                  </Box>
                ) : (
                  <div className="mt-5 rounded-xl border border-dashed border-slate-300 bg-slate-50/80 px-4 py-5 text-center text-sm text-slate-600 dark:border-slate-700/90 dark:bg-slate-950/50 dark:text-slate-500 sm:px-6">
                    {mode === "bootstrap"
                      ? "Сделайте снимок или выберите файл — превью появится здесь."
                      : "Камера или файл — кадр появится здесь."}
                  </div>
                )}

                {mode === "bootstrap" ? (
                  <div className="mt-5">
                    <FaceLabBootstrapPanel
                      pin={selectedPin}
                      file={file}
                      onSaved={afterBootstrapSave}
                      onCameraGuidanceAngleChange={setCameraBootstrapAngle}
                    />
                  </div>
                ) : null}

                <AnimatePresence initial={false} mode="popLayout">
                  {file && mode !== "bootstrap" ? (
                    <motion.div
                      key="face-lab-submit"
                      layout
                      initial={{ opacity: 0, scale: 0.94, y: 14 }}
                      animate={{ opacity: 1, scale: 1, y: 0 }}
                      exit={{ opacity: 0, scale: 0.96, y: 10 }}
                      transition={{
                        type: "spring",
                        stiffness: 420,
                        damping: 30,
                        mass: 0.88,
                      }}
                      className="mt-6 flex w-full flex-col items-center md:mt-7"
                    >
                      <Button
                        variant="contained"
                        size="large"
                        color="primary"
                        disabled={busy}
                        onClick={() => void onSubmit()}
                        sx={{
                          minHeight: 56,
                          px: 4,
                          py: 1.5,
                          width: "100%",
                          maxWidth: { md: 520 },
                          borderRadius: 2,
                          textTransform: "none",
                          fontSize: { xs: "1rem", md: "1.05rem" },
                          fontWeight: 700,
                          boxShadow: "0 4px 16px rgba(37, 99, 235, 0.32)",
                          transition:
                            "box-shadow 0.15s ease, transform 0.12s ease",
                          "&:hover": {
                            boxShadow: "0 6px 22px rgba(37, 99, 235, 0.38)",
                          },
                          "&:disabled": {
                            boxShadow: "none",
                          },
                        }}
                      >
                        {busy
                          ? mode === "search"
                            ? "Ищем по базе…"
                            : "Сверяем с эталоном…"
                          : mode === "search"
                            ? "Запустить поиск"
                            : "Сверить с эталоном"}
                      </Button>
                    </motion.div>
                  ) : null}
                </AnimatePresence>
              </motion.section>
            </motion.div>
          </motion.div>

          <AnimatePresence mode="popLayout">
            <motion.div
              key="face-lab-results"
              layout
              initial={{ opacity: 0, scale: 0.97, y: 12, x: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0, x: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8, x: 6 }}
              transition={springLayoutMain}
              className="min-w-0 space-y-5 lg:col-span-7 xl:col-span-8"
            >
              <PrimaryStateCard spec={primaryStateSpec} busy={busy} />

              {padWarning && padWarningFriendly ? (
                <motion.div
                  className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm dark:border-amber-800/50 dark:bg-amber-950/20"
                  initial={{ opacity: 0, y: 14, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ type: "spring", stiffness: 340, damping: 26 }}
                >
                  <p className="font-medium text-amber-900 dark:text-amber-200">
                    {padWarningFriendly.title}
                  </p>
                  {padWarningFriendly.detail ? (
                    <p className="mt-1 text-amber-800/90 dark:text-amber-200/85">
                      {padWarningFriendly.detail}
                    </p>
                  ) : null}
                </motion.div>
              ) : null}

              {error && errorFriendly ? (
                <motion.div
                  className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-950 dark:border-amber-800/50 dark:bg-amber-950/25 dark:text-amber-100"
                  initial={{ opacity: 0, y: 14, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ type: "spring", stiffness: 340, damping: 26 }}
                >
                  <p className="font-medium text-amber-950 dark:text-amber-100">
                    {errorFriendly.title}
                  </p>
                  {errorFriendly.detail ? (
                    <p className="mt-2 text-sm text-amber-800/90 dark:text-amber-200/90">
                      {errorFriendly.detail}
                    </p>
                  ) : null}
                </motion.div>
              ) : null}

              {padResult ? (
                <motion.section
                  className="space-y-3"
                  initial={{ opacity: 0, y: 16, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ type: "spring", stiffness: 320, damping: 24 }}
                >
                  <details className="rounded-2xl border border-slate-200/90 bg-slate-50/90 dark:border-slate-700/70 dark:bg-slate-900/40">
                    <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-slate-700 dark:text-slate-200 [&::-webkit-details-marker]:hidden">
                      Проверка фото
                    </summary>
                    <div className="border-t border-slate-200/80 p-3 dark:border-slate-700/70">
                      <PadResultPanel pad={padResult} />
                    </div>
                  </details>
                </motion.section>
              ) : null}

              {verifyResult !== null ? (
                <motion.section
                  className="space-y-3 pb-4"
                  initial={{ opacity: 0, y: 18, scale: 0.97 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{
                    type: "spring",
                    stiffness: 300,
                    damping: 23,
                    delay: 0.04,
                  }}
                >
                  <motion.h2
                    className="text-xs font-semibold uppercase text-slate-500"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.08 }}
                  >
                    {mode === "search" ? "Распознавание" : "Сравнение"}
                  </motion.h2>
                  {mode === "search" ? (
                    <RecognizeOrRaw data={verifyResult} />
                  ) : (
                    <VerifyOrRaw data={verifyResult} />
                  )}
                </motion.section>
              ) : null}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </ThemeProvider>
  );
};

export default FaceLabPage;
