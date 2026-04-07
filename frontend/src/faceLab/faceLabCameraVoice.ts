import { Howl } from "howler";
import { isAxiosError } from "axios";
import localforage from "localforage";
import axiosInstance from "../api";
import type { CameraGuidanceContext } from "./camera/types";
import { faceLabLog } from "./faceLabLog";

export type FaceLabVoiceLang = "off" | "ru" | "kk" | "en";

const PHASE: Record<
  string,
  Record<Exclude<FaceLabVoiceLang, "off">, string>
> = {
  loading: {
    ru: "Пожалуйста, подождите несколько секунд — мы готовим проверку.",
    kk: "Өтінеміз, бірнеше секунд күтіңіз — тексеруді дайындаймыз.",
    en: "Please wait a moment while we prepare the check for you.",
  },
  blink: {
    ru: "Пожалуйста, один раз моргните.",
    kk: "Өтінеміз, көзіңізді бір рет жұмыңыз.",
    en: "Please blink once, when you are ready.",
  },
  yaw: {
    ru: "Пожалуйста, слегка поверните голову влево или вправо.",
    kk: "Өтінеміз, басыңызды сәл солға немесе оңға бұраңыз.",
    en: "Please turn your head gently to the left or to the right.",
  },
  smile: {
    ru: "Пожалуйста, слегка улыбнитесь.",
    kk: "Өтінеміз, жеңіл күлімсіреңіз.",
    en: "Please give a slight smile, if you would.",
  },
  unavailable: {
    ru: "К сожалению, в этом браузере проверка недоступна. Вы можете снять кадр вручную — спасибо за понимание.",
    kk: "Өкінішке орай, бұл браузерде тексеру қолжетімсіз. Суретті қолмен түсіре аласыз — түсінгеніңізге рахмет.",
    en: "We are sorry — this check is not available in this browser. You may take a photo manually. Thank you for your understanding.",
  },
};

const SETUP_TTS_PHASE_KEYS = [
  "setup_profile_photo",
  "setup_bootstrap_front",
  "setup_bootstrap_left",
  "setup_bootstrap_right",
] as const;

export const FACE_LAB_TTS_PHASE_KEYS: readonly string[] = Object.freeze([
  ...Object.keys(PHASE),
  ...SETUP_TTS_PHASE_KEYS,
]);

const TTS_IDB_VERSION = "v_5";

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

const SETUP_GUIDE: Record<
  Exclude<CameraGuidanceContext, "default">,
  Record<Exclude<FaceLabVoiceLang, "off">, string>
> = {
  profile_photo: {
    ru: "Пожалуйста, смотрите прямо в камеру. В светлой рамке на видео показан силуэт головы фронтально; совместите своё лицо с ним и нажмите затвор.",
    kk: "Өтінеміз, камераға тік қараңыз. Бейнедегі жарық рамка ішінде беттің алдыңғы силуэті көрсетілген; бетіңізді сәйкестендіріп, түсіріңіз батырмасын басыңыз.",
    en: "Please look straight at the camera. Inside the bright frame you will see a front-facing head silhouette; align your face with it, then tap the shutter.",
  },
  bootstrap_front: {
    ru: "Пожалуйста, встаньте прямо перед камерой. В рамке на видео — силуэт головы анфас; повторите положение примерно как на макете, затем сделайте снимок.",
    kk: "Өтінеміз, камера алдында тік тұрыңыз. Рамкадағы бейнеде беттің алдыңғы силуэті бар; макеттегідей орналастырып, сурет түсіріңіз.",
    en: "Please stand squarely in front of the camera. The frame shows a front-facing head silhouette; match your pose to it, then take the photo.",
  },
  bootstrap_left: {
    ru: "Пожалуйста, слегка поверните голову влево примерно на двадцать градусов — разворот лица к камере, не наклон ухом к плечу. В рамке анимация: лицо уходит вглубь экрана; повторите и снимите.",
    kk: "Өтінеміз, басыңызды шамамен жиырма градусқа солға бұраңыз — бетті камераға бұраңыз, құлақты иіспей. Рамкадағы анимация бетті экран тереңіне қарай бұрады; соған сәйкестендіріп түсіріңіз.",
    en: "Please turn your head slightly left, about twenty degrees — swivel your face toward the camera, not an ear-to-shoulder tilt. The animation in the frame shows the face turning in depth; match it, then capture.",
  },
  bootstrap_right: {
    ru: "Пожалуйста, слегка поверните голову вправо примерно на двадцать градусов — разворот лица к камере, не наклон ухом к плечу. В рамке анимация: лицо уходит вглубь экрана; повторите и снимите.",
    kk: "Өтінеміз, басыңызды шамамен жиырма градусқа оңға бұраңыз — бетті камераға бұраңыз, құлақты иіспей. Рамкадағы анимация бетті экран тереңіне қарай бұрады; соған сәйкестендіріп түсіріңіз.",
    en: "Please turn your head slightly right, about twenty degrees — swivel your face toward the camera, not an ear-to-shoulder tilt. The animation in the frame shows the face turning in depth; match it, then capture.",
  },
};

export function phraseForSetupGuidance(
  ctx: CameraGuidanceContext,
  lang: FaceLabVoiceLang,
): string | null {
  if (lang === "off" || ctx === "default") return null;
  const row = SETUP_GUIDE[ctx];
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
