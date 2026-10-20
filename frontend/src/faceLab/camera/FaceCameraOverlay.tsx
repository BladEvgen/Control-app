import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useRef,
  useState,
  useEffect,
} from "react";
import { createPortal, flushSync } from "react-dom";
import { AnimatePresence, MotionConfig, motion } from "framer-motion";
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
  optimizeCameraTrackForFace,
  computeVideoMirror,
  isWebKitCameraConservativeMode,
  applyCameraPointOfInterest,
} from "./camera-device";
import type { FaceLabVoiceLang } from "../faceLabCameraVoice";
import {
  livenessPhaseHasVoice,
  setupGuidancePhaseKey,
  speakFaceLab,
  cancelFaceLabSpeech,
  isFaceLabSpeechCancelled,
} from "../faceLabCameraVoice";
import { faceLabLog } from "../faceLabLog";
import { capturePhoto } from "./camera-capture";
import { useCameraFrame } from "./useCameraFrame";
import {
  VideoFrame,
  AspectMask,
  FaceOval,
  GridOverlay,
  ThumbnailPreview,
  ErrorDisplay,
  FullscreenPreview,
} from "./CameraUIComponents";
import { TopControls, BottomControls } from "./CameraControls";
import { camLog } from "./cameraLog";
import {
  LivenessGuide,
  useFaceLiveness,
  type LivenessPhase,
  type PoseGuidePose,
} from "../liveness";
import { cameraGuidanceMessage } from "./cameraGuidanceMessage";

type Props = {
  onShot: (blob: Blob) => void;
  requireLiveness?: boolean;
  voiceLang?: FaceLabVoiceLang;
  guidanceContext?: CameraGuidanceContext;
};

const SETUP_TITLE: Record<CameraGuidanceContext, string> = {
  default: "Сделайте снимок",
  profile_photo: "Снимок для профиля",
  bootstrap_front: "Посмотрите прямо",
  bootstrap_left: "Голову чуть влево",
  bootstrap_right: "Голову чуть вправо",
};

const SETUP_POSE: Record<CameraGuidanceContext, PoseGuidePose> = {
  default: "front",
  profile_photo: "front",
  bootstrap_front: "front",
  bootstrap_left: "turn_left",
  bootstrap_right: "turn_right",
};

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
  const [lastShotUrl, setLastShotUrl] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [isCapturing, setIsCapturing] = useState(false);
  const [focusPoint, setFocusPoint] = useState<{ x: number; y: number } | null>(
    null,
  );
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
  const cameraSessionIdRef = useRef(0);
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
    onLoadError: (reason, error) =>
      faceLabLog.warn("Browser liveness unavailable", { reason, error }),
  });
  const livenessRunning = requireLiveness && !livenessSkipped;

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
    cancelFaceLabSpeech();
    if (phaseAtSchedule === "passed") return;
    const delay = phaseAtSchedule === "loading" ? 400 : 60;
    const id = window.setTimeout(() => {
      if (!openRef.current) return;
      const phNow = livenessPhaseRef.current;
      if (phNow === "idle") return;
      if (!livenessPhaseHasVoice(phNow, voiceLang)) return;
      if (lastAnnouncedVoicePhaseRef.current === phNow) return;
      lastAnnouncedVoicePhaseRef.current = phNow;
      void speakFaceLab({
        phase: phNow,
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
    const phaseKey = setupGuidancePhaseKey(guidanceContext, voiceLang);
    if (!phaseKey) return;
    const delay = window.setTimeout(() => {
      if (!openRef.current) return;
      cancelFaceLabSpeech();
      void speakFaceLab({
        phase: phaseKey,
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
      setShowManualCaptureAction(false);
      return;
    }
    const timer = window.setTimeout(() => {
      setShowManualCaptureAction(true);
    }, 6500);
    return () => {
      window.clearTimeout(timer);
    };
  }, [open, requireLiveness, livenessSkipped, liveness.phase]);

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

      let optimizeRequested = false;
      const handleVideoReady = () => {
        if (cancelled || !video.videoWidth || !video.videoHeight) return;
        if (!didLogStreamDims) {
          didLogStreamDims = true;
          camLog.info("Camera stream", {
            size: `${video.videoWidth}x${video.videoHeight}`,
          });
        }
        bumpReady();
        if (optimizeRequested) return;
        optimizeRequested = true;
        void optimizeCameraTrackForFace(trackRef.current).then((after) => {
          if (
            cancelled ||
            !after?.width ||
            !after?.height ||
            conservative ||
            didLogAfterMaxResolution
          ) {
            return;
          }
          didLogAfterMaxResolution = true;
          camLog.info(
            "Camera controls applied",
            `${after.width}x${after.height}`,
          );
        });
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
            bumpReady();
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
      sessionId: number,
    ): Promise<"ok" | "denied" | "notfound" | "failed"> => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: constraints,
        });
        if (cameraSessionIdRef.current !== sessionId || !openRef.current) {
          stream.getTracks().forEach((track) => track.stop());
          return "failed";
        }
        await attachStream(stream, {
          mirrorIfUnlabeled,
          streamFacing,
        });
        if (cameraSessionIdRef.current !== sessionId || !openRef.current) {
          stream.getTracks().forEach((track) => track.stop());
          stopStream();
          return "failed";
        }
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
    [attachStream, stopStream],
  );

  const startCamera = useCallback(
    async (side: Facing) => {
      const sessionId = ++cameraSessionIdRef.current;
      setError(null);
      stopStream();

      let last: "denied" | "notfound" | "failed" = "failed";

      const mirrorHint = side === "user";
      const immediateCandidates = createHighQualityConstraints(undefined, side);
      for (const constraints of immediateCandidates) {
        if (cameraSessionIdRef.current !== sessionId || !openRef.current)
          return;
        const result = await tryOpenCamera(
          constraints,
          mirrorHint,
          side,
          sessionId,
        );
        if (result === "ok") {
          if (cameraSessionIdRef.current !== sessionId || !openRef.current) {
            stopStream();
            return;
          }
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

      if (cameraSessionIdRef.current !== sessionId || !openRef.current) return;
      const devices = await listVideoDevices();
      devicesRef.current = devices;
      const primaryDeviceId = pickPrimaryCamera(devices, side);
      const constraintsCandidates = createHighQualityConstraints(
        primaryDeviceId || undefined,
        side,
      );

      for (const constraints of constraintsCandidates) {
        if (cameraSessionIdRef.current !== sessionId || !openRef.current)
          return;
        const result = await tryOpenCamera(
          constraints,
          side === "user",
          side,
          sessionId,
        );
        if (result === "ok") {
          if (cameraSessionIdRef.current !== sessionId || !openRef.current) {
            stopStream();
            return;
          }
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

    setIsCameraReady(false);
    vibrate([15]);
    await startCamera(nextFacing);
  }, [facing, startCamera]);

  const manualShutterLocked =
    requireLiveness &&
    !livenessSkipped &&
    liveness.phase !== "unavailable" &&
    liveness.phase !== "passed";

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

      void (async () => {
        let gotBlob: Blob | null = null;
        try {
          const v = videoRef.current;
          const c = containerRef.current;
          if (!v || !c) {
            setError("Не удалось сделать снимок");
            setIsCapturing(false);
            capturingRef.current = false;
            if (fromAuto) {
              autoCaptureDoneRef.current = false;
            }
            return;
          }
          gotBlob = await capturePhoto({
            video: v,
            frame,
            container: c,
            shouldMirror,
          });

          if (gotBlob) {
            playShutterSound();
            if (!fromAuto) {
              const previewUrl = URL.createObjectURL(gotBlob);
              setLastShotUrl((prev) => {
                if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
                return previewUrl;
              });
            }
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
          setIsCapturing(false);
          capturingRef.current = false;
          if (fromAuto && !gotBlob) {
            autoCaptureDoneRef.current = false;
          }
        }
      })();
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

    void handleCaptureRef.current(true);
  }, [open, requireLiveness, livenessSkipped, liveness.phase, isCameraReady]);

  const handleClose = useCallback(() => {
    cameraSessionIdRef.current += 1;
    cancelFaceLabSpeech();
    stopStream();
    setLastShotUrl((prev) => {
      if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
      return null;
    });
    setPreviewOpen(false);
    setOpen(false);
    setLivenessSkipped(false);
    autoCaptureDoneRef.current = false;
  }, [stopStream]);

  handleCloseRef.current = handleClose;

  const handleTapToFocusPointer = useCallback(
    async (event: React.PointerEvent) => {
      const video = videoRef.current;
      const track = trackRef.current;

      if (!video || !track?.applyConstraints) return;
      try {
        const rect = video.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width;
        const y = (event.clientY - rect.top) / rect.height;
        setFocusPoint({ x: event.clientX, y: event.clientY });
        await applyCameraPointOfInterest(track, { x, y });
        vibrate([10]);
        window.setTimeout(() => setFocusPoint(null), 620);
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
      cameraSessionIdRef.current += 1;
      setLivenessSkipped(false);
      autoCaptureDoneRef.current = false;
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
        <MotionConfig reducedMotion="user">
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
                <FaceOval
                  frame={frame}
                  state={
                    livenessRunning && liveness.phase === "passed"
                      ? "ok"
                      : "active"
                  }
                  progress={
                    livenessRunning && liveness.plan.length > 0
                      ? (liveness.stepIndex +
                          (liveness.phase === "passed"
                            ? 0
                            : liveness.progress)) /
                        liveness.plan.length
                      : null
                  }
                />
                <GridOverlay visible={gridOn} frame={frame} aspect={aspect} />

                <AnimatePresence>
                  {focusPoint && (
                    <motion.div
                      key={`${focusPoint.x}-${focusPoint.y}`}
                      className="pointer-events-none fixed z-[10010] h-16 w-16 rounded-full border-2 border-white/90 shadow-[0_0_0_9999px_rgba(0,0,0,0.02)]"
                      style={{
                        left: focusPoint.x - 32,
                        top: focusPoint.y - 32,
                      }}
                      initial={{ opacity: 0, scale: 1.35 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.78 }}
                      transition={{ duration: 0.18, ease: "easeOut" }}
                    />
                  )}
                </AnimatePresence>

                <AnimatePresence>
                  {lastShotUrl && !previewOpen && (
                    <ThumbnailPreview
                      imageUrl={lastShotUrl}
                      onOpen={() => setPreviewOpen(true)}
                    />
                  )}
                </AnimatePresence>

                <ErrorDisplay error={error} onClose={() => setError(null)} />

                <div className="pointer-events-none absolute inset-x-0 top-[max(68px,calc(env(safe-area-inset-top,0px)+60px))] z-40 flex flex-col items-center gap-3 px-3 md:top-[76px]">
                  {livenessRunning ? (
                    <LivenessGuide
                      phase={liveness.phase}
                      hint={displayLivenessHint || liveness.hint}
                      plan={liveness.plan}
                      stepIndex={liveness.stepIndex}
                      progress={liveness.progress}
                    />
                  ) : (
                    <LivenessGuide
                      phase="face"
                      plan={[]}
                      stepIndex={0}
                      progress={0}
                      title={
                        requireLiveness
                          ? "Сделайте снимок кнопкой внизу"
                          : SETUP_TITLE[guidanceContext]
                      }
                      pose={
                        requireLiveness ? "front" : SETUP_POSE[guidanceContext]
                      }
                      hint={cameraGuidanceMessage(
                        guidanceContext,
                        requireLiveness,
                      )}
                    />
                  )}

                  {livenessRunning &&
                    showManualCaptureAction &&
                    liveness.phase !== "passed" &&
                    liveness.phase !== "idle" && (
                      <button
                        type="button"
                        className="pointer-events-auto min-h-11 rounded-full bg-white/15 px-5 text-sm font-medium text-white ring-1 ring-white/25 backdrop-blur-md transition-colors hover:bg-white/25 focus:outline-none focus-visible:ring-4 focus-visible:ring-white/70"
                        onClick={() => setLivenessSkipped(true)}
                      >
                        Не получается? Снять вручную
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
                      : isCapturing
                        ? "Снимаем…"
                        : liveness.phase === "unavailable"
                          ? "Сделать снимок вручную"
                          : isCameraReady && !isCapturing
                            ? "Сделать снимок"
                            : null
                  }
                />
              </motion.div>
            </motion.div>
          </AnimatePresence>
        </MotionConfig>,
        document.body,
      )}

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
