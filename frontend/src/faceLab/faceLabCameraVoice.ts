import { Howl } from "howler";
import { isAxiosError } from "axios";
import localforage from "localforage";
import axiosInstance from "../api";

export type FaceLabVoiceLang = "off" | "ru" | "kk" | "en";

const PHASE: Record<
  string,
  Record<Exclude<FaceLabVoiceLang, "off">, string>
> = {
  loading: {
    ru: "Секунду, готовим проверку.",
    kk: "Бір секунд, тексеруді дайындаймыз.",
    en: "One moment, we are getting the check ready.",
  },
  blink: {
    ru: "Моргните один раз, пожалуйста.",
    kk: "Көзіңізді бір рет жұмыңыз, өтінеміз.",
    en: "Please blink once.",
  },
  yaw: {
    ru: "Слегка поверните голову в сторону: влево или вправо, пожалуйста.",
    kk: "Басыңызды сәл жаққа бұраңыз: солға немесе оңға, өтінеміз.",
    en: "Please turn your head slightly to the side — left or right.",
  },
  smile: {
    ru: "Слегка улыбнитесь, пожалуйста.",
    kk: "Жеңіл күлімсіреңіз, өтінеміз.",
    en: "Please smile a little.",
  },
  unavailable: {
    ru: "В этом браузере проверка недоступна. Можно снять кадр вручную.",
    kk: "Бұл браузерде тексеру жоқ. Суретті қолмен ала аласыз.",
    en: "This check is not available in this browser. You can take a photo manually.",
  },
};

export const FACE_LAB_TTS_PHASE_KEYS: readonly string[] = Object.freeze(
  Object.keys(PHASE),
);

const TTS_IDB_VERSION = "v_1";

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

export function phraseForLivenessPhase(
  phase: string,
  lang: FaceLabVoiceLang,
): string | null {
  if (lang === "off") return null;
  const row = PHASE[phase];
  if (!row) return null;
  const line = row[lang] ?? row.ru;
  return line.trim() ? line : null;
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

export function isFaceLabSpeechCancelled(e: unknown): e is FaceLabSpeechCancelled {
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
  if (typeof window !== "undefined" && window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
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

function speakFaceLabBrowserAsync(
  text: string,
  lang: Exclude<FaceLabVoiceLang, "off">,
): Promise<void> {
  if (typeof window === "undefined" || !text.trim()) return Promise.resolve();
  const synth = window.speechSynthesis;
  if (!synth) return Promise.resolve();
  synth.cancel();
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang === "kk" ? "kk-KZ" : lang === "en" ? "en-US" : "ru-RU";
    u.rate = 1.02;
    u.volume = 1;
    u.onend = () => resolve();
    u.onerror = () => resolve();
    synth.speak(u);
  });
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
  text: string;
  lang: Exclude<FaceLabVoiceLang, "off">;
};


export async function speakFaceLab(opts: SpeakFaceLabOptions): Promise<void> {
  const { phase, text, lang } = opts;
  if (typeof window === "undefined" || !text.trim()) return;

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
      if (holder.mine != null && inFlightSpeech === holder.mine) inFlightSpeech = null;
      resolve();
    };
    const finishErr = (e: unknown) => {
      if (settled) return;
      settled = true;
      if (holder.mine != null && inFlightSpeech === holder.mine) inFlightSpeech = null;
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
          await speakFaceLabBrowserAsync(text, lang);
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
            if (import.meta.env.DEV) {
              console.warn("Face Lab TTS load error", err);
            }
            stopHowl();
            void speakFaceLabBrowserAsync(text, lang).then(finishOk, finishOk);
          },
          onplayerror: (_id, err) => {
            if (import.meta.env.DEV) {
              console.warn("Face Lab TTS play error", err);
            }
            stopHowl();
            void speakFaceLabBrowserAsync(text, lang).then(finishOk, finishOk);
          },
        });

        currentHowl.play();
      } catch (e: unknown) {
        if (isAxiosError(e) && e.code === "ERR_CANCELED") {
          finishErr(new FaceLabSpeechCancelled());
          return;
        }
        stopHowl();
        try {
          await speakFaceLabBrowserAsync(text, lang);
          finishOk();
        } catch {
          finishOk();
        }
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
