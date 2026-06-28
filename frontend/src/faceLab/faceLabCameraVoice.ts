import { Howl } from "howler";
import { isAxiosError } from "axios";
import localforage from "localforage";
import axiosInstance from "../api";
import type { CameraGuidanceContext } from "./camera/types";
import { faceLabLog } from "./faceLabLog";

export type FaceLabVoiceLang = "off" | "ru" | "kk" | "en";

const LIVENESS_PHASE_KEYS = [
  "loading",
  "blink",
  "yaw",
  "smile",
  "unavailable",
] as const;

const SETUP_TTS_PHASE_KEYS = [
  "setup_profile_photo",
  "setup_bootstrap_front",
  "setup_bootstrap_left",
  "setup_bootstrap_right",
] as const;

const SETUP_CONTEXT_TO_PHASE: Record<
  Exclude<CameraGuidanceContext, "default">,
  string
> = {
  profile_photo: "setup_profile_photo",
  bootstrap_front: "setup_bootstrap_front",
  bootstrap_left: "setup_bootstrap_left",
  bootstrap_right: "setup_bootstrap_right",
};

export const FACE_LAB_TTS_PHASE_KEYS: readonly string[] = Object.freeze([
  ...LIVENESS_PHASE_KEYS,
  ...SETUP_TTS_PHASE_KEYS,
]);

const TTS_IDB_VERSION = "v_6";

const ttsStore = localforage.createInstance({
  name: "control_front",
  storeName: "face_lab_tts_mp3",
  description: "Face Lab TTS (MP3 blobs)",
});

function idbKey(phase: string, lang: string): string {
  return `${TTS_IDB_VERSION}:${phase}:${lang}`;
}

function memKey(phase: string, lang: string): string {
  return `${phase}:${lang}`;
}

const memoryBlobs = new Map<string, Blob>();
const inflightLoads = new Map<string, Promise<Blob | null>>();

export function livenessPhaseHasVoice(
  phase: string,
  lang: FaceLabVoiceLang,
): boolean {
  if (lang === "off") return false;
  return (LIVENESS_PHASE_KEYS as readonly string[]).includes(phase);
}

export function setupGuidancePhaseKey(
  ctx: CameraGuidanceContext,
  lang: FaceLabVoiceLang,
): string | null {
  if (lang === "off" || ctx === "default") return null;
  return SETUP_CONTEXT_TO_PHASE[ctx] ?? null;
}

let lastSpeakDedupeKey = "";
let ttsAbortController: AbortController | null = null;
let currentHowl: Howl | null = null;
let objectUrlToRevoke: string | null = null;

export class FaceLabSpeechCancelled extends Error {
  constructor() {
    super("Face Lab speech cancelled");
    this.name = "FaceLabSpeechCancelled";
  }
}

export function isFaceLabSpeechCancelled(
  e: unknown,
): e is FaceLabSpeechCancelled {
  return e instanceof FaceLabSpeechCancelled;
}

type SpeechWait = { resolve: () => void; reject: (e: unknown) => void };
let inFlightSpeech: SpeechWait | null = null;

function revokeObjectUrl(): void {
  if (objectUrlToRevoke) {
    URL.revokeObjectURL(objectUrlToRevoke);
    objectUrlToRevoke = null;
  }
}

function stopHowl(): void {
  if (currentHowl) {
    currentHowl.stop();
    currentHowl.unload();
    currentHowl = null;
  }
  revokeObjectUrl();
}

function abortAndStopPlayback(): void {
  ttsAbortController?.abort();
  ttsAbortController = null;
  stopHowl();
}

export function cancelFaceLabSpeech(): void {
  abortAndStopPlayback();
  lastSpeakDedupeKey = "";
  if (inFlightSpeech) {
    const w = inFlightSpeech;
    inFlightSpeech = null;
    w.reject(new FaceLabSpeechCancelled());
  }
}

async function loadTtsBlob(
  phase: string,
  lang: Exclude<FaceLabVoiceLang, "off">,
  signal?: AbortSignal,
): Promise<Blob | null> {
  if (typeof window === "undefined") return null;

  const mk = memKey(phase, lang);
  const cached = memoryBlobs.get(mk);
  if (cached && cached.size > 0) return cached;

  try {
    const fromIdb = await ttsStore.getItem<Blob>(idbKey(phase, lang));
    if (fromIdb && fromIdb.size > 0) {
      memoryBlobs.set(mk, fromIdb);
      return fromIdb;
    }
  } catch {
    /* ignore */
  }

  if (signal !== undefined) {
    try {
      const res = await axiosInstance.get("/face-lab/tts/", {
        params: { phase, lang },
        responseType: "blob",
        timeout: 60000,
        signal,
      });
      const blob = res.data as Blob;
      if (!blob || blob.size === 0) return null;
      memoryBlobs.set(mk, blob);
      void ttsStore.setItem(idbKey(phase, lang), blob).catch(() => {});
      return blob;
    } catch (e: unknown) {
      if (isAxiosError(e) && e.code === "ERR_CANCELED") throw e;
      return null;
    }
  }

  const existing = inflightLoads.get(mk);
  if (existing) return existing;

  const task = (async (): Promise<Blob | null> => {
    try {
      const res = await axiosInstance.get("/face-lab/tts/", {
        params: { phase, lang },
        responseType: "blob",
        timeout: 60000,
      });
      const blob = res.data as Blob;
      if (!blob || blob.size === 0) return null;
      memoryBlobs.set(mk, blob);
      void ttsStore.setItem(idbKey(phase, lang), blob).catch(() => {});
      return blob;
    } catch {
      return null;
    } finally {
      inflightLoads.delete(mk);
    }
  })();

  inflightLoads.set(mk, task);
  return task;
}

export async function warmFaceLabTtsVoicePack(
  lang: Exclude<FaceLabVoiceLang, "off">,
): Promise<void> {
  if (typeof window === "undefined") return;
  await Promise.all(
    FACE_LAB_TTS_PHASE_KEYS.map((phase) =>
      loadTtsBlob(phase, lang).catch(() => null),
    ),
  );
}

export type SpeakFaceLabOptions = {
  phase: string;
  lang: Exclude<FaceLabVoiceLang, "off">;
};

export async function speakFaceLab(opts: SpeakFaceLabOptions): Promise<void> {
  const { phase, lang } = opts;
  if (typeof window === "undefined") return;

  const dedupeKey = `${phase}:${lang}`;
  if (dedupeKey === lastSpeakDedupeKey) return;
  lastSpeakDedupeKey = dedupeKey;
  window.setTimeout(() => {
    if (lastSpeakDedupeKey === dedupeKey) lastSpeakDedupeKey = "";
  }, 1800);

  return new Promise<void>((resolve, reject) => {
    let settled = false;
    const holder: { mine: SpeechWait | null } = { mine: null };
    const finishOk = () => {
      if (settled) return;
      settled = true;
      if (holder.mine != null && inFlightSpeech === holder.mine)
        inFlightSpeech = null;
      resolve();
    };
    const finishErr = (e: unknown) => {
      if (settled) return;
      settled = true;
      if (holder.mine != null && inFlightSpeech === holder.mine)
        inFlightSpeech = null;
      reject(e);
    };

    holder.mine = { resolve: finishOk, reject: finishErr };

    if (inFlightSpeech) {
      const w = inFlightSpeech;
      inFlightSpeech = null;
      w.reject(new FaceLabSpeechCancelled());
    }
    inFlightSpeech = holder.mine;

    void (async () => {
      try {
        abortAndStopPlayback();

        const ac = new AbortController();
        ttsAbortController = ac;

        const blob = await loadTtsBlob(phase, lang, ac.signal);
        if (ttsAbortController !== ac) {
          finishErr(new FaceLabSpeechCancelled());
          return;
        }
        if (!blob || blob.size === 0) {
          faceLabLog.warn(
            "TTS: нет MP3 с сервера, озвучка пропущена",
            phase,
            lang,
          );
          finishOk();
          return;
        }

        const url = URL.createObjectURL(blob);
        objectUrlToRevoke = url;

        currentHowl = new Howl({
          src: [url],
          format: ["mp3"],
          html5: true,
          onend: () => {
            stopHowl();
            finishOk();
          },
          onloaderror: (_id, err) => {
            faceLabLog.warn("TTS load error", err);
            stopHowl();
            finishOk();
          },
          onplayerror: (_id, err) => {
            faceLabLog.warn("TTS play error", err);
            stopHowl();
            finishOk();
          },
        });

        currentHowl.play();
      } catch (e: unknown) {
        if (isAxiosError(e) && e.code === "ERR_CANCELED") {
          finishErr(new FaceLabSpeechCancelled());
          return;
        }
        stopHowl();
        faceLabLog.warn("TTS: сбой загрузки", e);
        finishOk();
      }
    })();
  });
}

export const FACE_LAB_VOICE_STORAGE_KEY = "faceLab_voice_lang";

export function readVoiceLang(): FaceLabVoiceLang {
  try {
    const v = localStorage.getItem(FACE_LAB_VOICE_STORAGE_KEY);
    if (v === "ru" || v === "kk" || v === "en" || v === "off") return v;
  } catch {
    /* ignore */
  }
  return "off";
}

export function persistVoiceLang(lang: FaceLabVoiceLang): void {
  try {
    localStorage.setItem(FACE_LAB_VOICE_STORAGE_KEY, lang);
  } catch {
    /* ignore */
  }
}
