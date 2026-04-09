import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useRef,
  useState,
  useEffect,
} from "react";
import { createPortal, flushSync } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import type {
  Aspect,
  CameraGuidanceContext,
  Facing,
  FaceCameraOverlayRef,
} from "./types";
import {
  vibrate,
  playShutterSound,
  defaultAspectForViewport,
} from "./camera-utils";
import {
  listVideoDevices,
  pickPrimaryCamera,
  createHighQualityConstraints,
  applyMaxVideoResolution,
  computeVideoMirror,
  isWebKitCameraConservativeMode,
} from "./camera-device";
import type { FaceLabVoiceLang } from "../faceLabCameraVoice";
import {
  phraseForLivenessPhase,
  phraseForSetupGuidance,
  speakFaceLab,
  cancelFaceLabSpeech,
  isFaceLabSpeechCancelled,
} from "../faceLabCameraVoice";
import { faceLabLog } from "../faceLabLog";
import {
  capturePhoto,
  createPreviewUrl,
  waitForVideoPipelineFrames,
} from "./camera-capture";
import { useCameraFrame } from "./useCameraFrame";
import {
  VideoFrame,
  AspectMask,
  ViewfinderBootstrapHint,
  GridOverlay,
  FlashEffect,
  ThumbnailPreview,
  ErrorDisplay,
  FullscreenPreview,
} from "./CameraUIComponents";
import { TopControls, BottomControls } from "./CameraControls";
import { camLog } from "./cameraLog";
import {
  useFaceLiveness,
  type LivenessPhase,
} from "../liveness/useFaceLiveness";
import { cameraGuidanceMessage } from "./cameraGuidanceMessage";

type Props = {
  onShot: (blob: Blob) => void;
  requireLiveness?: boolean;
  voiceLang?: FaceLabVoiceLang;
  guidanceContext?: CameraGuidanceContext;
};

function overlayPhaseBadge(
  phase: LivenessPhase,
  requireLiveness: boolean,
  skipped: boolean,
): string {
  if (!requireLiveness) return "Подсказка";
  if (skipped) return "Ручной снимок";
  if (phase === "loading") return "Подготовка";
  if (phase === "face") return "Шаг 1";
  if (phase === "blink") return "Шаг 2";
  if (phase === "yaw") return "Шаг 3";
  if (phase === "smile") return "Финал";
  if (phase === "passed") return "Готово";
  if (phase === "unavailable") return "Ручной снимок";
  return "Подсказка";
}

function overlayPhaseTitle(
  phase: LivenessPhase,
  requireLiveness: boolean,
  skipped: boolean,
  guidanceContext: CameraGuidanceContext,
): string {
  if (!requireLiveness) {
    if (guidanceContext === "bootstrap_front") return "Снимите прямой портрет";
    if (guidanceContext === "bootstrap_left") return "Поверните лицо влево";
    if (guidanceContext === "bootstrap_right") return "Поверните лицо вправо";
    if (guidanceContext === "profile_photo") return "Снимите кадр профиля";
    return "Снимите кадр";
  }
  if (skipped) return "Снимите кадр вручную";
  if (phase === "loading") return "Готовим проверку";
  if (phase === "face") return "Поставьте лицо в рамку";
  if (phase === "blink") return "Моргните один раз";
  if (phase === "yaw") return "Поверните голову";
  if (phase === "smile") return "Посмотрите прямо и слегка улыбнитесь";
  if (phase === "passed") return "Кадр готов";
  if (phase === "unavailable") return "Проверка недоступна";
  return "Держите лицо в рамке";
}

function FaceCameraOverlayInner(
  {
    onShot,
    requireLiveness = true,
    voiceLang = "off",
    guidanceContext = "default",
  }: Props,
  ref: React.Ref<FaceCameraOverlayRef>,
) {
  const [open, setOpen] = useState(false);
  const openRef = useRef(false);
  openRef.current = open;
  const [facing, setFacing] = useState<Facing>("user");
  const [error, setError] = useState<string | null>(null);
  const [gridOn, setGridOn] = useState(true);
  const [aspect, setAspect] = useState<Aspect>("4:3");
  const aspectUserChosenRef = useRef(false);

  useEffect(() => {
    if (aspectUserChosenRef.current) return;
    setAspect(defaultAspectForViewport());
  }, []);

  const handleAspectChange = useCallback((next: Aspect) => {
    aspectUserChosenRef.current = true;
    setAspect(next);
  }, []);
  const [flash, setFlash] = useState(false);
  const [lastShotUrl, setLastShotUrl] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [isCapturing, setIsCapturing] = useState(false);
  const [shouldMirror, setShouldMirror] = useState(false);
  const [isCameraReady, setIsCameraReady] = useState(false);
  const [livenessSkipped, setLivenessSkipped] = useState(false);
  const [showManualCaptureAction, setShowManualCaptureAction] = useState(false);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const trackRef = useRef<MediaStreamTrack | null>(null);
  const attachStreamCleanupRef = useRef<(() => void) | null>(null);
  const devicesRef = useRef<MediaDeviceInfo[]>([]);
  const capturingRef = useRef(false);
  const autoCaptureDoneRef = useRef(false);
  const handleCaptureRef = useRef<(fromAuto?: boolean) => Promise<void>>(
    async () => {},
  );
  const handleCloseRef = useRef<() => void>(() => {});

  const { frame, recomputeFrame } = useCameraFrame(
    aspect,
    containerRef,
    videoRef,
  );

  const liveness = useFaceLiveness({
    videoRef,
    active: open && requireLiveness,
    skipped: livenessSkipped || !requireLiveness,
  });

  const phaseForVoiceRef = useRef<LivenessPhase | string>("");
  const lastAnnouncedVoicePhaseRef = useRef<string>("");

  const [displayLivenessHint, setDisplayLivenessHint] = useState("");
  const hintDebounceRef = useRef<number | null>(null);
  const livenessPhaseRef = useRef(liveness.phase);
  const livenessHintRef = useRef(liveness.hint);
  livenessPhaseRef.current = liveness.phase;
  livenessHintRef.current = liveness.hint;

  useEffect(() => {
    if (!open) {
      setDisplayLivenessHint("");
      phaseForVoiceRef.current = "";
      if (hintDebounceRef.current != null) {
        window.clearTimeout(hintDebounceRef.current);
        hintDebounceRef.current = null;
      }
      return;
    }
    const ph = liveness.phase;
    const h = liveness.hint;
    if (hintDebounceRef.current != null) {
      window.clearTimeout(hintDebounceRef.current);
      hintDebounceRef.current = null;
    }
    if (ph !== phaseForVoiceRef.current) {
      phaseForVoiceRef.current = ph;
      setDisplayLivenessHint(h);
      return;
    }
    hintDebounceRef.current = window.setTimeout(() => {
      hintDebounceRef.current = null;
      if (livenessPhaseRef.current !== ph) return;
      setDisplayLivenessHint(livenessHintRef.current);
    }, 320);
    return () => {
      if (hintDebounceRef.current != null) {
        window.clearTimeout(hintDebounceRef.current);
        hintDebounceRef.current = null;
      }
    };
  }, [open, liveness.phase, liveness.hint]);

  useEffect(() => {
    if (!open) {
      lastAnnouncedVoicePhaseRef.current = "";
      cancelFaceLabSpeech();
      return;
    }
    if (voiceLang === "off" || !requireLiveness || livenessSkipped) return;
    const phaseAtSchedule = liveness.phase;
    if (phaseAtSchedule === "idle") return;
    if (phaseAtSchedule === "passed" && requireLiveness && !livenessSkipped)
      return;

    cancelFaceLabSpeech();
    const delay = phaseAtSchedule === "loading" ? 400 : 60;
    const id = window.setTimeout(() => {
      if (!openRef.current) return;
      const phNow = livenessPhaseRef.current;
      if (phNow === "idle") return;
      const line = phraseForLivenessPhase(phNow, voiceLang);
      if (!line) return;
      if (lastAnnouncedVoicePhaseRef.current === phNow) return;
      lastAnnouncedVoicePhaseRef.current = phNow;
      void speakFaceLab({
        phase: phNow,
        text: line,
        lang: voiceLang,
      }).catch((e: unknown) => {
        if (!isFaceLabSpeechCancelled(e)) {
          faceLabLog.warn("TTS liveness", e);
        }
      });
    }, delay);

    return () => {
      window.clearTimeout(id);
    };
  }, [open, voiceLang, requireLiveness, livenessSkipped, liveness.phase]);

  useEffect(() => {
    if (!open || voiceLang === "off" || requireLiveness) return;
    const text = phraseForSetupGuidance(guidanceContext, voiceLang);
    if (!text) return;
    const phaseKey = `setup_${guidanceContext}`;
    const delay = window.setTimeout(() => {
      if (!openRef.current) return;
      cancelFaceLabSpeech();
      void speakFaceLab({
        phase: phaseKey,
        text,
        lang: voiceLang,
      }).catch((e: unknown) => {
        if (!isFaceLabSpeechCancelled(e)) {
          faceLabLog.warn("TTS setup", e);
        }
      });
    }, 450);
    return () => {
      window.clearTimeout(delay);
    };
  }, [open, voiceLang, requireLiveness, guidanceContext]);

  useEffect(() => {
    if (!open || !requireLiveness || livenessSkipped) {
      setShowManualCaptureAction(false);
      return;
    }
    if (liveness.phase === "passed") {
      setShowManualCaptureAction(false);
      return;
    }
    if (liveness.phase === "unavailable") {
      setShowManualCaptureAction(true);
      return;
    }
    const timer = window.setTimeout(() => {
      setShowManualCaptureAction(true);
    }, 6500);
    return () => {
      window.clearTimeout(timer);
    };
  }, [open, requireLiveness, livenessSkipped, liveness.phase]);

  const overlayGuidanceText =
    !requireLiveness && guidanceContext !== "default"
      ? ""
      : requireLiveness && !livenessSkipped
        ? displayLivenessHint ||
          cameraGuidanceMessage(guidanceContext, requireLiveness)
        : cameraGuidanceMessage(guidanceContext, requireLiveness);

  const stopStream = useCallback(() => {
    attachStreamCleanupRef.current?.();
    attachStreamCleanupRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    trackRef.current = null;
    const video = videoRef.current;
    if (video) video.srcObject = null;
    setIsCameraReady(false);
  }, []);

  const attachStream = useCallback(
    async (
      stream: MediaStream,
      opts: { mirrorIfUnlabeled?: boolean; streamFacing: Facing },
    ) => {
      const video = videoRef.current;
      if (!video) return;

      setIsCameraReady(false);

      attachStreamCleanupRef.current?.();
      attachStreamCleanupRef.current = null;

      streamRef.current = stream;
      trackRef.current = stream.getVideoTracks()[0] || null;
      video.srcObject = stream;
      video.muted = true;
      video.playsInline = true;
      video.setAttribute("playsinline", "true");
      video.setAttribute("webkit-playsinline", "true");
      video.setAttribute("x5-playsinline", "true");

      const track = trackRef.current;
      const mirrorIfUnlabeled = Boolean(opts.mirrorIfUnlabeled);
      if (track) {
        const settings = track.getSettings();
        const deviceId = settings.deviceId;
        const device = devicesRef.current.find((d) => d.deviceId === deviceId);
        setShouldMirror(
          computeVideoMirror({
            deviceLabel: device?.label,
            mirrorIfUnlabeled,
            streamFacing: opts.streamFacing,
          }),
        );
      } else {
        setShouldMirror(
          computeVideoMirror({
            deviceLabel: undefined,
            mirrorIfUnlabeled,
            streamFacing: opts.streamFacing,
          }),
        );
      }

      const conservative = isWebKitCameraConservativeMode();
      const failMs = conservative ? 5200 : 1800;

      let cancelled = false;
      const playKickTimers: number[] = [];
      let didLogStreamDims = false;
      let didLogAfterMaxResolution = false;

      const bumpReady = () => {
        if (cancelled) return;
        if (video.videoWidth && video.videoHeight) {
          setIsCameraReady(true);
          recomputeFrame();
        }
      };

      const handleVideoReady = () => {
        void (async () => {
          if (cancelled || !video.videoWidth || !video.videoHeight) return;
          if (!didLogStreamDims) {
            didLogStreamDims = true;
            camLog.info("Camera stream", {
              beforeMax: `${video.videoWidth}x${video.videoHeight}`,
            });
          }
          const after = await applyMaxVideoResolution(trackRef.current);
          if (cancelled) return;
          if (
            after?.width &&
            after?.height &&
            !conservative &&
            !didLogAfterMaxResolution
          ) {
            didLogAfterMaxResolution = true;
            camLog.info(
              "Applied max resolution",
              `${after.width}x${after.height}`,
            );
          }
          bumpReady();
        })();
      };

      const kickPlay = () => {
        if (cancelled) return;
        void video.play().catch(() => {});
      };

      const onLoadedMeta = () => {
        kickPlay();
      };

      const onUnmute = () => {
        kickPlay();
        handleVideoReady();
      };

      const onVideoResize = () => bumpReady();

      video.addEventListener("loadedmetadata", onLoadedMeta);
      video.addEventListener("loadeddata", handleVideoReady);
      video.addEventListener("canplay", handleVideoReady);
      video.addEventListener("playing", bumpReady);
      video.addEventListener("resize", onVideoResize);
      track?.addEventListener("unmute", onUnmute);

      [40, 120, 350, 800, 1800].forEach((ms) => {
        playKickTimers.push(
          window.setTimeout(() => {
            if (cancelled) return;
            kickPlay();
            if (video.videoWidth && video.videoHeight) {
              handleVideoReady();
            }
          }, ms),
        );
      });

      const timer = window.setTimeout(() => {
        if (!video.videoWidth || !video.videoHeight) {
          stream.getTracks().forEach((t) => t.stop());
          video.srcObject = null;
          setIsCameraReady(false);
        }
      }, failMs);

      const readyBumpTimer = window.setTimeout(
        () => {
          if (video.videoWidth && video.videoHeight) {
            window.clearTimeout(timer);
            void applyMaxVideoResolution(trackRef.current).then(() => {
              if (!cancelled) bumpReady();
            });
          }
        },
        conservative ? 2400 : 1600,
      );

      attachStreamCleanupRef.current = () => {
        cancelled = true;
        window.clearTimeout(timer);
        window.clearTimeout(readyBumpTimer);
        playKickTimers.forEach((tid) => window.clearTimeout(tid));
        track?.removeEventListener("unmute", onUnmute);
        video.removeEventListener("loadedmetadata", onLoadedMeta);
        video.removeEventListener("loadeddata", handleVideoReady);
        video.removeEventListener("canplay", handleVideoReady);
        video.removeEventListener("playing", bumpReady);
        video.removeEventListener("resize", onVideoResize);
      };

      kickPlay();
      try {
        await video.play();
      } catch {
        kickPlay();
      }
    },
    [recomputeFrame],
  );

  const tryOpenCamera = useCallback(
    async (
      constraints: MediaTrackConstraints,
      mirrorIfUnlabeled: boolean | undefined,
      streamFacing: Facing,
    ): Promise<"ok" | "denied" | "notfound" | "failed"> => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: constraints,
        });
        await attachStream(stream, {
          mirrorIfUnlabeled,
          streamFacing,
        });
        const video = videoRef.current!;
        return video.srcObject ? "ok" : "failed";
      } catch (e: unknown) {
        const name =
          e && typeof e === "object" && "name" in e
            ? String((e as DOMException).name)
            : "";
        if (name === "NotAllowedError" || name === "PermissionDeniedError") {
          return "denied";
        }
        if (name === "NotFoundError" || name === "DevicesNotFoundError") {
          return "notfound";
        }
        return "failed";
      }
    },
    [attachStream],
  );

  const startCamera = useCallback(
    async (side: Facing) => {
      setError(null);
      stopStream();

      let last: "denied" | "notfound" | "failed" = "failed";

      // Сначала getUserMedia с facingMode — без await enumerateDevices до запроса,
      // иначе Chrome часто теряет user activation и не показывает системный диалог.
      const mirrorHint = side === "user";
      const immediateCandidates = createHighQualityConstraints(undefined, side);
      for (const constraints of immediateCandidates) {
        const result = await tryOpenCamera(constraints, mirrorHint, side);
        if (result === "ok") {
          setFacing(side);
          try {
            devicesRef.current = await listVideoDevices();
            const tid = trackRef.current?.getSettings().deviceId;
            const dev = devicesRef.current.find((d) => d.deviceId === tid);
            setShouldMirror(
              computeVideoMirror({
                deviceLabel: dev?.label,
                mirrorIfUnlabeled: mirrorHint,
                streamFacing: side,
              }),
            );
          } catch {
            devicesRef.current = [];
          }
          camLog.info("Camera started");
          return;
        }
        if (result === "denied") {
          last = "denied";
        } else if (result === "notfound") {
          last = "notfound";
        }
      }

      const devices = await listVideoDevices();
      devicesRef.current = devices;
      const primaryDeviceId = pickPrimaryCamera(devices, side);
      const constraintsCandidates = createHighQualityConstraints(
        primaryDeviceId || undefined,
        side,
      );

      for (const constraints of constraintsCandidates) {
        const result = await tryOpenCamera(constraints, side === "user", side);
        if (result === "ok") {
          setFacing(side);
          try {
            const tid = trackRef.current?.getSettings().deviceId;
            const dev = devicesRef.current.find((d) => d.deviceId === tid);
            setShouldMirror(
              computeVideoMirror({
                deviceLabel: dev?.label,
                mirrorIfUnlabeled: side === "user",
                streamFacing: side,
              }),
            );
          } catch {
            /* keep mirrorHint */
          }
          camLog.info("Camera started");
          return;
        }
        if (result === "denied") {
          last = "denied";
        } else if (result === "notfound") {
          last = "notfound";
        }
      }

      if (last === "denied") {
        setError(
          "Доступ к камере запрещён. Разрешите камеру для этого сайта в настройках браузера и откройте съёмку снова.",
        );
      } else if (last === "notfound") {
        setError(
          "Камера не найдена или недоступна. Проверьте подключение устройства.",
        );
      } else {
        setError(
          "Не удалось открыть камеру (устройство занято или не поддерживается).",
        );
      }
    },
    [stopStream, tryOpenCamera],
  );

  const toggleFacing = useCallback(async () => {
    const nextFacing: Facing = facing === "user" ? "environment" : "user";
    const nextDeviceId = pickPrimaryCamera(devicesRef.current, nextFacing);

    setIsCameraReady(false);
    vibrate([15]);

    const track = trackRef.current as MediaStreamTrack & {
      applyConstraints?: (c: MediaTrackConstraints) => Promise<void>;
    };

    if (track?.applyConstraints && nextDeviceId) {
      try {
        await track.applyConstraints({ deviceId: { exact: nextDeviceId } });
        setFacing(nextFacing);

        const device = devicesRef.current.find(
          (d) => d.deviceId === nextDeviceId,
        );
        if (device) {
          setShouldMirror(
            computeVideoMirror({
              deviceLabel: device.label,
              mirrorIfUnlabeled: nextFacing === "user",
              streamFacing: nextFacing,
            }),
          );
        }

        const video = videoRef.current;
        if (video && video.videoWidth && video.videoHeight) {
          setTimeout(() => {
            void applyMaxVideoResolution(trackRef.current).then(() => {
              setIsCameraReady(true);
              recomputeFrame();
            });
          }, 300);
        }
        return;
      } catch {
        /* fall through */
      }
    }

    await startCamera(nextFacing);
  }, [facing, startCamera, recomputeFrame]);

  const manualShutterLocked = requireLiveness && !livenessSkipped;

  const handleCapture = useCallback(
    async (fromAuto = false) => {
      const video = videoRef.current;
      const container = containerRef.current;

      if (!fromAuto && manualShutterLocked) {
        return;
      }
      if (
        !video ||
        !container ||
        !isCameraReady ||
        isCapturing ||
        capturingRef.current
      ) {
        return;
      }

      if (fromAuto) {
        autoCaptureDoneRef.current = true;
      }

      setIsCapturing(true);
      capturingRef.current = true;
      setFlash(true);

      window.setTimeout(() => {
        void (async () => {
          let gotBlob: Blob | null = null;
          try {
            await new Promise<void>((r) => void window.setTimeout(r, 220));
            const v = videoRef.current;
            const c = containerRef.current;
            if (!v || !c) {
              setError("Не удалось сделать снимок");
              setFlash(false);
              setIsCapturing(false);
              capturingRef.current = false;
              if (fromAuto) {
                autoCaptureDoneRef.current = false;
              }
              return;
            }
            await waitForVideoPipelineFrames(v, 5);
            playShutterSound();
            if (!fromAuto) {
              const previewUrl = createPreviewUrl(v, frame, c, shouldMirror);
              if (previewUrl) {
                setLastShotUrl(previewUrl);
              }
            }

            gotBlob = await capturePhoto({
              video: v,
              frame,
              container: c,
              shouldMirror,
              maxWidth: 1600,
              maxHeight: 1600,
              quality: 0.92,
            });

            if (gotBlob) {
              onShot(gotBlob);
              if (fromAuto) {
                window.setTimeout(() => handleCloseRef.current(), 320);
              }
            } else {
              setError("Не удалось сделать снимок");
            }
          } catch (err) {
            camLog.info("Capture error:", err);
            setError("Не удалось сделать снимок");
          } finally {
            setFlash(false);
            setIsCapturing(false);
            capturingRef.current = false;
            if (fromAuto && !gotBlob) {
              autoCaptureDoneRef.current = false;
            }
          }
        })();
      }, 0);
    },
    [
      frame,
      onShot,
      isCapturing,
      isCameraReady,
      shouldMirror,
      manualShutterLocked,
    ],
  );

  handleCaptureRef.current = handleCapture;

  useEffect(() => {
    if (!open || !requireLiveness || livenessSkipped) {
      autoCaptureDoneRef.current = false;
      return;
    }
    if (liveness.phase !== "passed") {
      autoCaptureDoneRef.current = false;
      return;
    }
    if (!isCameraReady || autoCaptureDoneRef.current) {
      return;
    }

    let cancelled = false;

    const run = async () => {
      await new Promise<void>((r) => window.setTimeout(r, 100));
      if (cancelled || !openRef.current) return;
      void handleCaptureRef.current(true);
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [open, requireLiveness, livenessSkipped, liveness.phase, isCameraReady]);

  const handleClose = useCallback(() => {
    cancelFaceLabSpeech();
    stopStream();
    setLastShotUrl(null);
    setPreviewOpen(false);
    setOpen(false);
    setLivenessSkipped(false);
    autoCaptureDoneRef.current = false;
  }, [stopStream]);

  handleCloseRef.current = handleClose;

  const handleTapToFocusPointer = useCallback(
    async (event: React.PointerEvent) => {
      const video = videoRef.current;
      const track = trackRef.current as MediaStreamTrack & {
        applyConstraints?: (c: MediaTrackConstraints) => Promise<void>;
        getCapabilities?: () => {
          focusMode?: string[];
        };
      };

      if (!video || !track?.applyConstraints) return;

      try {
        const capabilities = track.getCapabilities?.() as {
          focusMode?: string[];
        };
        if (
          !capabilities?.focusMode ||
          !Array.isArray(capabilities.focusMode)
        ) {
          return;
        }

        const rect = video.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width;
        const y = (event.clientY - rect.top) / rect.height;

        await track.applyConstraints({
          advanced: [
            {
              pointsOfInterest: [{ x, y }],
            } as unknown as MediaTrackConstraintSet,
          ],
        });

        vibrate([10]);
      } catch {
        /* optional */
      }
    },
    [],
  );

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) {
        stopStream();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () =>
      document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [stopStream]);

  const resetLiveness = liveness.reset;

  const resetSession = useCallback(() => {
    setLastShotUrl((prev) => {
      if (prev?.startsWith("blob:")) {
        URL.revokeObjectURL(prev);
      }
      return null;
    });
    setPreviewOpen(false);
    setLivenessSkipped(false);
    autoCaptureDoneRef.current = false;
    resetLiveness();
  }, [resetLiveness]);

  useImperativeHandle(ref, () => ({
    open: async (side: Facing = "user") => {
      setLivenessSkipped(false);
      autoCaptureDoneRef.current = false;
      // Иначе startCamera вызывается до commit: videoRef ещё null — поток не цепляется и запрос камеры ведёт себя странно.
      flushSync(() => {
        setOpen(true);
      });
      await new Promise<void>((resolve) => {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => resolve());
        });
      });
      await startCamera(side);
    },
    close: handleClose,
    isActive: () => !!streamRef.current,
    resetSession,
  }));

  if (!open) return null;

  return (
    <>
      {createPortal(
        <AnimatePresence>
          <motion.div
            className="fixed inset-0 z-[9999] bg-black/80 p-0 backdrop-blur-sm md:p-5"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            role="dialog"
            aria-modal="true"
          >
            <motion.div
              ref={containerRef}
              onClick={(e) => e.stopPropagation()}
              className="relative mx-auto h-[100dvh] w-screen overflow-hidden rounded-none bg-black md:h-[min(86dvh,780px)] md:min-h-[min(86dvh,780px)] md:w-[min(96vw,1280px)] md:rounded-2xl md:ring-1 md:ring-white/10"
              initial={{ y: 16, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 8, opacity: 0 }}
              transition={{ type: "spring", stiffness: 240, damping: 22 }}
            >
              <VideoFrame
                videoRef={videoRef}
                shouldMirror={shouldMirror}
                onTapToFocus={handleTapToFocusPointer}
              />

              <AspectMask frame={frame} aspect={aspect} />
              <ViewfinderBootstrapHint
                frame={frame}
                context={guidanceContext}
              />
              <GridOverlay visible={gridOn} frame={frame} aspect={aspect} />

              <AnimatePresence>
                {lastShotUrl && !previewOpen && (
                  <ThumbnailPreview
                    imageUrl={lastShotUrl}
                    onOpen={() => setPreviewOpen(true)}
                  />
                )}
              </AnimatePresence>

              <ErrorDisplay error={error} onClose={() => setError(null)} />

              <div className="pointer-events-none absolute left-0 right-0 top-[max(52px,calc(env(safe-area-inset-top,0px)+40px))] z-40 flex flex-col items-center gap-3 px-4 md:top-[60px]">
                <div className="pointer-events-none flex max-w-xl flex-col items-center gap-2">
                  <div className="inline-flex rounded-full border border-white/20 bg-black/40 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-white/85 shadow-lg backdrop-blur-md">
                    {overlayPhaseBadge(
                      liveness.phase,
                      requireLiveness,
                      livenessSkipped,
                    )}
                  </div>
                  <div className="pointer-events-none max-w-xl rounded-[1.35rem] border border-white/15 bg-black/45 px-4 py-3 text-center text-white shadow-xl backdrop-blur-md">
                    <p className="text-sm font-semibold leading-snug sm:text-[0.98rem]">
                      {overlayPhaseTitle(
                        liveness.phase,
                        requireLiveness,
                        livenessSkipped,
                        guidanceContext,
                      )}
                    </p>
                    {overlayGuidanceText ? (
                      <p className="mt-1 text-xs leading-relaxed text-white/82 sm:text-sm">
                        {overlayGuidanceText}
                      </p>
                    ) : null}
                  </div>
                </div>

                {requireLiveness &&
                  open &&
                  !livenessSkipped &&
                  showManualCaptureAction &&
                  liveness.phase !== "passed" &&
                  liveness.phase !== "idle" && (
                    <button
                      type="button"
                      className="pointer-events-auto rounded-full bg-white/15 px-4 py-2 text-sm font-medium text-white ring-1 ring-white/20 backdrop-blur-md hover:bg-white/25"
                      onClick={() => setLivenessSkipped(true)}
                    >
                      Снять вручную
                    </button>
                  )}
              </div>

              <TopControls
                onClose={handleClose}
                gridOn={gridOn}
                onToggleGrid={() => setGridOn((prev) => !prev)}
                aspect={aspect}
                onAspectChange={handleAspectChange}
              />

              <BottomControls
                lastShotUrl={lastShotUrl}
                onDone={handleClose}
                isCapturing={isCapturing}
                isCameraReady={isCameraReady}
                onCapture={() => void handleCapture(false)}
                onToggleFacing={toggleFacing}
                shouldMirror={shouldMirror}
                captureDisabled={manualShutterLocked}
                captureHint={
                  manualShutterLocked
                    ? liveness.phase === "passed"
                      ? "Сохраняем кадр…"
                      : null
                    : isCameraReady && !isCapturing
                      ? "Сделать снимок"
                      : null
                }
              />
            </motion.div>
          </motion.div>
        </AnimatePresence>,
        document.body,
      )}
      {createPortal(<FlashEffect visible={flash} />, document.body)}

      {createPortal(
        <AnimatePresence>
          {previewOpen && lastShotUrl && (
            <FullscreenPreview
              imageUrl={lastShotUrl}
              onClose={() => setPreviewOpen(false)}
            />
          )}
        </AnimatePresence>,
        document.body,
      )}
    </>
  );
}

export default forwardRef(FaceCameraOverlayInner);
