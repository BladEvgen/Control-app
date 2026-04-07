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
import { fileForPadUpload } from "../faceLab/faceLabPadResize";
import { useMuiDarkSync } from "../faceLab/useMuiDarkSync";
import {
  readVoiceLang,
  persistVoiceLang,
  warmFaceLabTtsVoicePack,
  type FaceLabVoiceLang,
} from "../faceLab/faceLabCameraVoice";
import {
  FaCamera,
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

const DEFAULT_OUTCOME_HEADLINE: Record<
  Exclude<SessionOutcome, "idle">,
  string
> = {
  success: "Готово",
  partial: "Частичный результат",
  fail: "Пока без подтверждения",
};

function padTrustStrong(pad: PadTestResponse | null): boolean {
  return pad !== null && pad.trust_confirmed === true;
}

function padTrustWeak(pad: PadTestResponse | null): boolean {
  return pad !== null && pad.trust_confirmed !== true;
}

function compareOutcomeFromContract(
  c: FaceVerifyApiResponse,
): FaceLabEvaluateResult {
  const summary = (c.summary || c.decision_summary || "").trim();
  if (c.matched && c.final_decision === "YES") {
    return {
      outcome: "success",
      headline: "Совпадение подтверждено",
      message: summary || "Совпадение подтверждено.",
    };
  }
  return {
    outcome: "fail",
    headline: "Совпадение не подтверждено",
    message: summary || "Совпадение не подтверждено.",
  };
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
        headline: "Проверка кадра не прошла",
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
        message:
          "В ответе verify нет результата PAD — обновите клиент или сервер.",
      };
    }
    return compareOutcomeFromContract(parsed);
  }

  if (padWarning) {
    const f = humanizePadFailureReason(padWarning);
    return {
      outcome: "fail",
      message: [f.title, f.detail].filter(Boolean).join(" "),
      headline: "Живость кадра не подтверждена",
    };
  }

  if (pad === null) {
    return {
      outcome: "fail",
      message:
        "Живость на сервере не проверена — переснимите и отправьте снова.",
      headline: "PAD не отработал",
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
      message: `Найдено в галерее: ${rec.recognized_staff.length}. Живость подтверждена.`,
    };
  }

  if (hits && padWeak) {
    return {
      outcome: "partial",
      message: "В галерее есть совпадения, живость без уверенного «да».",
      headline: "Живость слабая",
    };
  }

  if (!hits && padStrong) {
    return {
      outcome: "partial",
      message:
        unknownN > 0
          ? "Лицо есть, живость ок, по базе ниже порога — другой ракурс или нет маски."
          : "Живость ок, по галерее пусто.",
      headline: "Не нашли",
    };
  }

  return {
    outcome: "partial",
    message: "Нет совпадений и живость не подтверждена — переснимите.",
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
      setError(
        "В режиме настройки входа сохраните кадр кнопкой в шагах слева — не через «Отправить на проверку».",
      );
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
      if (mode === "search") {
        try {
          const padFile = await fileForPadUpload(file);
          const fdPad = new FormData();
          fdPad.append("image", padFile);
          const res = await axiosInstance.post<PadTestResponse>(
            "face-lab/pad-test/",
            fdPad,
            { timeout: FACE_LAB_HEAVY_REQUEST_MS },
          );
          padLocal = res.data;
          setPadResult(res.data);
        } catch (padErr: unknown) {
          setPadResult(null);
          if (axios.isAxiosError(padErr) && padErr.response?.data) {
            padWarnLocal =
              typeof padErr.response.data === "object" &&
              padErr.response.data !== null &&
              "error" in padErr.response.data
                ? String((padErr.response.data as { error: string }).error)
                : "Сбой проверки живости";
          } else {
            padWarnLocal =
              padErr instanceof Error
                ? padErr.message
                : "Сбой проверки живости";
          }
          setPadWarning(padWarnLocal);
        }
      } else {
        setPadResult(null);
        setPadWarning(null);
      }

      const fd = new FormData();
      fd.append("image", file);
      const headers = authBearerHeaders();

      if (mode === "search") {
        const res = await axios.post(`${apiUrl}/recognize-faces/`, fd, {
          headers,
          timeout: FACE_LAB_HEAVY_REQUEST_MS,
        });
        verifyLocal = res.data;
        setVerifyResult(res.data);
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

  const outcomeBannerTitle =
    sessionOutcome !== "idle"
      ? (outcomeHeadline ?? DEFAULT_OUTCOME_HEADLINE[sessionOutcome])
      : "";

  const hasWideResults =
    busy ||
    padResult !== null ||
    verifyResult !== null ||
    padWarning !== null ||
    error !== null ||
    sessionOutcome !== "idle" ||
    (mode === "bootstrap" && (!!selectedPin || !!file));

  const springLayoutMain = {
    type: "spring" as const,
    stiffness: 260,
    damping: 21,
    mass: 0.92,
  };

  return (
    <ThemeProvider theme={muiTheme}>
      <div className="mx-auto w-full max-w-[88rem] px-3 py-6 text-slate-900 dark:text-slate-100 sm:px-5 sm:py-8 md:px-8 lg:px-10 lg:py-10 pb-[max(1.5rem,env(safe-area-inset-bottom))]">
        <Breadcrumbs items={[{ label: "Face Lab", path: undefined }]} />

        <header className="mb-6 border-b border-slate-200 pb-5 dark:border-slate-800/90 sm:mb-8 sm:pb-6">
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl md:text-4xl">
            Face Lab
          </h1>
          <p className="mt-2 max-w-xl text-sm text-slate-600 dark:text-slate-400">
            Проверка кадра, поиск по базе, сравнение с профилем или пошаговая
            настройка трёх ракурсов для входа.
          </p>
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

        <div className="grid grid-cols-1 gap-8 md:gap-10 lg:grid-cols-12 lg:gap-12 lg:items-start">
          <motion.div
            layout
            transition={springLayoutMain}
            className={
              hasWideResults
                ? "min-w-0 space-y-8 sm:space-y-10 lg:col-span-5"
                : "min-w-0 space-y-8 sm:space-y-10 lg:col-span-12"
            }
          >
            <motion.div
              layout
              transition={springLayoutMain}
              className={hasWideResults ? "w-full" : "mx-auto w-full max-w-xl"}
            >
              <section className="rounded-2xl border border-slate-200/90 bg-white/95 p-4 shadow-md shadow-slate-200/30 dark:border-slate-600/80 dark:bg-slate-900/55 dark:shadow-black/25 sm:p-5 md:p-6">
                <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500 sm:mb-4">
                  Режим
                </h2>
                <Box className="relative rounded-xl border border-slate-200/80 bg-slate-100/90 p-1 dark:border-slate-600 dark:bg-slate-950">
                  <motion.div
                    className="pointer-events-none absolute bottom-1 top-1 rounded-lg bg-white shadow-md ring-1 ring-slate-200/60 dark:bg-slate-600 dark:shadow-none dark:ring-slate-500/40"
                    initial={false}
                    animate={{
                      left:
                        mode === "search"
                          ? 4
                          : mode === "compare"
                            ? "calc(33.333% + 1px)"
                            : "calc(66.666% - 2px)",
                      width: "calc(33.333% - 6px)",
                    }}
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  />
                  <div className="relative z-10 grid min-h-[3rem] grid-cols-3 gap-0">
                    <button
                      type="button"
                      className={`flex min-h-[3rem] items-center justify-center gap-1.5 rounded-lg px-1.5 py-2.5 text-center text-xs font-semibold leading-snug transition-colors sm:min-h-0 sm:gap-2 sm:px-2 sm:py-3.5 sm:text-sm ${
                        mode === "search"
                          ? "text-slate-900 dark:text-white"
                          : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
                      }`}
                      onClick={() => {
                        setMode("search");
                        setError(null);
                        resetSessionFromScratch();
                      }}
                    >
                      <FaSearch
                        className="h-4 w-4 shrink-0 opacity-80"
                        aria-hidden
                      />
                      Поиск
                    </button>
                    <button
                      type="button"
                      className={`flex min-h-[3rem] items-center justify-center gap-1.5 rounded-lg px-1.5 py-2.5 text-center text-xs font-semibold leading-snug transition-colors sm:min-h-0 sm:gap-2 sm:px-2 sm:py-3.5 sm:text-sm ${
                        mode === "compare"
                          ? "text-slate-900 dark:text-white"
                          : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
                      }`}
                      onClick={() => {
                        setMode("compare");
                        setError(null);
                        resetSessionFromScratch();
                      }}
                    >
                      <FaUserCheck
                        className="h-4 w-4 shrink-0 opacity-80"
                        aria-hidden
                      />
                      <span className="leading-tight">Эталон</span>
                    </button>
                    <button
                      type="button"
                      className={`flex min-h-[3rem] flex-col items-center justify-center gap-0.5 rounded-lg px-1.5 py-2 text-center text-xs font-semibold leading-tight transition-colors sm:min-h-0 sm:flex-row sm:gap-1.5 sm:py-3.5 sm:text-sm ${
                        mode === "bootstrap"
                          ? "text-slate-900 dark:text-white"
                          : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
                      }`}
                      onClick={() => {
                        setMode("bootstrap");
                        setError(null);
                        resetSessionFromScratch();
                      }}
                    >
                      <FaUserPlus
                        className="h-4 w-4 shrink-0 opacity-80"
                        aria-hidden
                      />
                      <span className="leading-tight">Настройка входа</span>
                    </button>
                  </div>
                </Box>
              </section>

              {(mode === "compare" || mode === "bootstrap") && (
                <section
                  className={`rounded-2xl border border-slate-200/90 bg-white/95 p-4 shadow-md shadow-slate-200/30 dark:border-slate-600/80 dark:bg-slate-900/55 dark:shadow-black/25 sm:p-5 md:p-6 ${
                    mode === "bootstrap"
                      ? "ring-1 ring-primary-500/10 dark:ring-primary-400/10"
                      : ""
                  }`}
                >
                  {mode === "bootstrap" ? (
                    <div className="mb-5 border-b border-slate-200/80 pb-4 dark:border-slate-600/60">
                      <h2 className="text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-50">
                        Настройка входа по лицу
                      </h2>
                      <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                        Выберите человека, снимите три ракурса по шагам — дальше
                        всё подскажем.
                      </p>
                    </div>
                  ) : (
                    <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Сотрудник
                    </h2>
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
                    />
                  )}
                  {mode === "bootstrap" ? (
                    <div className="mt-2">
                      <FaceLabBootstrapPanel
                        pin={selectedPin}
                        file={file}
                        onSaved={afterBootstrapSave}
                        onCameraGuidanceAngleChange={setCameraBootstrapAngle}
                      />
                    </div>
                  ) : null}
                </section>
              )}

              <motion.section
                layout
                transition={springLayoutMain}
                className="rounded-2xl border border-slate-200/90 bg-white/95 p-4 shadow-md shadow-slate-200/30 dark:border-slate-600/80 dark:bg-slate-900/55 dark:shadow-black/25 sm:p-5 md:p-6"
              >
                <Stack
                  direction={{ xs: "column", sm: "row" }}
                  spacing={1.5}
                  alignItems={{ sm: "center" }}
                  justifyContent="space-between"
                  className="mb-5"
                >
                  <div>
                    <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      {mode === "bootstrap"
                        ? "Снимок для текущего шага"
                        : "Фото"}
                    </h2>
                    {mode === "bootstrap" ? (
                      <p className="mt-1 max-w-md text-sm text-slate-600 dark:text-slate-400">
                        Камера или файл — затем вернитесь к шагам выше и
                        сохраните кадр.
                      </p>
                    ) : null}
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
                    sx={{
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
                        borderColor: "divider",
                        "&.Mui-selected": {
                          bgcolor: "primary.main",
                          color: "primary.contrastText",
                          borderColor: "primary.main",
                          "&:hover": { bgcolor: "primary.dark" },
                        },
                      },
                    }}
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
                    sx={{
                      minHeight: 52,
                      py: 1.35,
                      px: 2,
                      flex: { sm: 1 },
                      borderRadius: 2,
                      borderWidth: 1.5,
                      textTransform: "none",
                      fontWeight: 600,
                      fontSize: "0.95rem",
                      transition:
                        "transform 0.12s ease, box-shadow 0.12s ease, border-color 0.12s ease",
                      "&:hover": {
                        borderColor: "primary.main",
                        bgcolor: "action.hover",
                        boxShadow: "0 2px 14px rgba(37, 99, 235, 0.14)",
                      },
                    }}
                  >
                    Камера
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
                    sx={{
                      minHeight: 52,
                      py: 1.35,
                      px: 2,
                      flex: { sm: 1 },
                      borderRadius: 2,
                      borderWidth: 1.5,
                      textTransform: "none",
                      fontWeight: 600,
                      fontSize: "0.95rem",
                      transition:
                        "transform 0.12s ease, box-shadow 0.12s ease, border-color 0.12s ease",
                      "&:hover": {
                        borderColor: "primary.main",
                        bgcolor: "action.hover",
                        boxShadow: "0 2px 14px rgba(37, 99, 235, 0.14)",
                      },
                    }}
                  >
                    Выбрать файл
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
                        letterSpacing={0.06}
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
                          className="h-4 w-4 shrink-0 text-primary-600 dark:text-primary-400"
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
                        {busy ? "Отправка…" : "Отправить на проверку"}
                      </Button>
                    </motion.div>
                  ) : null}
                </AnimatePresence>
              </motion.section>
            </motion.div>
          </motion.div>

          <AnimatePresence mode="popLayout">
            {hasWideResults ? (
              <motion.div
                key="face-lab-results"
                layout
                initial={{ opacity: 0, scale: 0.93, y: 16, x: 12 }}
                animate={{ opacity: 1, scale: 1, y: 0, x: 0 }}
                exit={{ opacity: 0, scale: 0.94, y: 10, x: 8 }}
                transition={springLayoutMain}
                className="min-w-0 space-y-8 sm:space-y-10 lg:col-span-7"
              >
                {mode === "bootstrap" && selectedPin && file ? (
                  <motion.section
                    className="rounded-2xl border border-primary-200/80 bg-primary-50/80 p-4 text-sm text-slate-700 shadow-sm dark:border-primary-900/40 dark:bg-primary-950/25 dark:text-slate-200 sm:p-4"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ type: "spring", stiffness: 320, damping: 26 }}
                  >
                    <p className="font-semibold text-slate-900 dark:text-slate-50">
                      Снимок готов
                    </p>
                    <p className="mt-1 leading-snug text-slate-600 dark:text-slate-300">
                      Сохраните текущий шаг в блоке настройки выше.
                    </p>
                  </motion.section>
                ) : null}

                {busy &&
                padResult === null &&
                verifyResult === null &&
                !padWarning &&
                !error &&
                sessionOutcome === "idle" ? (
                  <motion.div
                    className="rounded-2xl border border-slate-200 bg-white/90 px-4 py-10 text-center text-sm text-slate-600 shadow-sm dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-400 sm:py-12"
                    initial={{ opacity: 0, scale: 0.96 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ type: "spring", stiffness: 360, damping: 28 }}
                  >
                    <LoaderComponent
                      fullscreen={false}
                      compact
                      inline
                      variant="bars"
                      showGlow={false}
                      message="Проверяем кадр на сервере…"
                      className="justify-center py-2"
                    />
                  </motion.div>
                ) : null}

                {sessionOutcome !== "idle" ? (
                  <motion.section
                    key={sessionOutcome}
                    className={`rounded-2xl border p-4 sm:p-5 md:p-6 ${
                      sessionOutcome === "success"
                        ? "border-emerald-200 bg-emerald-50 dark:border-emerald-700/70 dark:bg-emerald-950/35"
                        : sessionOutcome === "partial"
                          ? "border-amber-200 bg-amber-50 dark:border-amber-700/60 dark:bg-amber-950/30"
                          : "border-rose-200 bg-rose-50 dark:border-rose-800/70 dark:bg-rose-950/25"
                    }`}
                    initial={{ opacity: 0, y: 20, scale: 0.97 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    transition={{
                      type: "spring" as const,
                      stiffness: 300,
                      damping: 22,
                      mass: 0.9,
                    }}
                  >
                    <motion.p
                      className={`text-base font-semibold sm:text-lg ${
                        sessionOutcome === "success"
                          ? "text-emerald-800 dark:text-emerald-200"
                          : sessionOutcome === "partial"
                            ? "text-amber-900 dark:text-amber-200"
                            : "text-rose-800 dark:text-rose-200"
                      }`}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: 0.05 }}
                    >
                      {outcomeBannerTitle}
                    </motion.p>
                    <motion.p
                      className="mt-2 text-sm leading-relaxed text-slate-700 dark:text-slate-300"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: 0.12 }}
                    >
                      {outcomeMessage}
                    </motion.p>
                  </motion.section>
                ) : null}

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
                    <motion.h2
                      className="text-xs font-semibold uppercase tracking-wider text-slate-500"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: 0.05 }}
                    >
                      Живость (сервер)
                    </motion.h2>
                    <PadResultPanel pad={padResult} />
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
                      className="text-xs font-semibold uppercase tracking-wider text-slate-500"
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
            ) : null}
          </AnimatePresence>
        </div>
      </div>
    </ThemeProvider>
  );
};

export default FaceLabPage;
