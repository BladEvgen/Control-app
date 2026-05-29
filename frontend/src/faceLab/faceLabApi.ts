import {
  parseFaceVerifyApiResponse,
  type FaceVerifyApiResponse,
} from "./faceVerificationSchema";
import {
  coercePadDiagnostics,
  type PadDiagnosticsPayload,
} from "./faceLabPadTypes";

export type { FaceVerifyApiResponse } from "./faceVerificationSchema";
export type { PadDiagnosticsPayload } from "./faceLabPadTypes";

export type PadTestResponse = {
  status: string;
  trust_confirmed: boolean | null;
  risk_score: number;
  tags: string[];
  model_version: string;
  elapsed_ms: number;
  deepface_score: number;
  device_score: number;
  frame_score: number;
  quality_penalty: number;
  device_bg_score: number;
  frame_global_score: number;
  recapture_score: number;
  face_reflection_score: number;
  diagnostics?: PadDiagnosticsPayload | null;
};

export function livenessToPadTestResponse(
  l: FaceVerifyApiResponse["liveness"],
): PadTestResponse | null {
  if (!l.checked) return null;
  const diag =
    l.diagnostics !== undefined && l.diagnostics !== null
      ? coercePadDiagnostics(l.diagnostics)
      : null;
  return {
    status: l.status ?? "pending",
    trust_confirmed: l.trust_confirmed ?? null,
    risk_score: typeof l.risk_score === "number" ? l.risk_score : 0,
    tags: Array.isArray(l.tags) ? l.tags : [],
    model_version: l.model_version ?? "",
    elapsed_ms: typeof l.elapsed_ms === "number" ? l.elapsed_ms : 0,
    deepface_score: typeof l.deepface_score === "number" ? l.deepface_score : 0,
    device_score: typeof l.device_score === "number" ? l.device_score : 0,
    frame_score: typeof l.frame_score === "number" ? l.frame_score : 0,
    quality_penalty:
      typeof l.quality_penalty === "number" ? l.quality_penalty : 0,
    device_bg_score:
      typeof l.device_bg_score === "number" ? l.device_bg_score : 0,
    frame_global_score:
      typeof l.frame_global_score === "number" ? l.frame_global_score : 0,
    recapture_score:
      typeof l.recapture_score === "number" ? l.recapture_score : 0,
    face_reflection_score:
      typeof l.face_reflection_score === "number" ? l.face_reflection_score : 0,
    ...(diag ? { diagnostics: diag } : {}),
  };
}

export type RecognizedStaffRow = {
  pin: string;
  name?: string;
  surname?: string;
  department?: string | null;
  similarity: number;
  neighbor_gap?: number;
  bbox: number[];
};

export type UnknownFaceRow = {
  status: string;
  bbox: number[];
  best_similarity?: number;
  neighbor_gap?: number;
};

export type RecognizeResponse = {
  recognized_staff: RecognizedStaffRow[];
  unknown_faces: UnknownFaceRow[];
};

export function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null;
}

export function normalizeScore01(x: number): number {
  if (!Number.isFinite(x)) return 0;
  if (x > 1 && x <= 100) return Math.min(1, Math.max(0, x / 100));
  if (x > 100) return 1;
  return Math.min(1, Math.max(0, x));
}

export function parsePadResult(data: unknown): PadTestResponse | null {
  if (!isRecord(data)) return null;
  const nums = [
    "risk_score",
    "elapsed_ms",
    "deepface_score",
    "device_score",
    "frame_score",
    "quality_penalty",
    "device_bg_score",
    "frame_global_score",
    "recapture_score",
    "face_reflection_score",
  ] as const;
  for (const k of nums) {
    if (typeof data[k] !== "number") return null;
  }
  if (typeof data.status !== "string") return null;
  if (
    data.trust_confirmed !== null &&
    typeof data.trust_confirmed !== "boolean"
  ) {
    return null;
  }
  if (
    !Array.isArray(data.tags) ||
    !data.tags.every((t) => typeof t === "string")
  ) {
    return null;
  }
  if (typeof data.model_version !== "string") return null;
  const diagRaw = data.diagnostics;
  const diagnostics =
    diagRaw !== undefined && diagRaw !== null
      ? coercePadDiagnostics(diagRaw)
      : null;
  const base: PadTestResponse = {
    status: data.status as string,
    trust_confirmed: data.trust_confirmed as boolean | null,
    risk_score: data.risk_score as number,
    tags: data.tags as string[],
    model_version: data.model_version as string,
    elapsed_ms: data.elapsed_ms as number,
    deepface_score: data.deepface_score as number,
    device_score: data.device_score as number,
    frame_score: data.frame_score as number,
    quality_penalty: data.quality_penalty as number,
    device_bg_score: data.device_bg_score as number,
    frame_global_score: data.frame_global_score as number,
    recapture_score: data.recapture_score as number,
    face_reflection_score: data.face_reflection_score as number,
  };
  if (diagnostics) {
    base.diagnostics = diagnostics;
  }
  return base;
}

export function parseRecognizeResponse(
  data: unknown,
): RecognizeResponse | null {
  if (!isRecord(data)) return null;
  if (
    !Array.isArray(data.recognized_staff) ||
    !Array.isArray(data.unknown_faces)
  ) {
    return null;
  }
  const recognized_staff: RecognizedStaffRow[] = [];
  for (const row of data.recognized_staff) {
    if (!isRecord(row)) return null;
    if (typeof row.pin !== "string" || typeof row.similarity !== "number") {
      return null;
    }
    if (
      !Array.isArray(row.bbox) ||
      !row.bbox.every((n) => typeof n === "number")
    ) {
      return null;
    }
    recognized_staff.push({
      pin: row.pin,
      name: typeof row.name === "string" ? row.name : undefined,
      surname: typeof row.surname === "string" ? row.surname : undefined,
      department:
        row.department === null || typeof row.department === "string"
          ? (row.department as string | null)
          : undefined,
      similarity: normalizeScore01(row.similarity),
      neighbor_gap:
        typeof row.neighbor_gap === "number"
          ? normalizeScore01(row.neighbor_gap)
          : undefined,
      bbox: row.bbox as number[],
    });
  }
  const unknown_faces: UnknownFaceRow[] = [];
  for (const row of data.unknown_faces) {
    if (!isRecord(row)) return null;
    if (typeof row.status !== "string") return null;
    if (
      !Array.isArray(row.bbox) ||
      !row.bbox.every((n) => typeof n === "number")
    ) {
      return null;
    }
    unknown_faces.push({
      status: row.status,
      bbox: row.bbox as number[],
      best_similarity:
        typeof row.best_similarity === "number"
          ? normalizeScore01(row.best_similarity)
          : undefined,
      neighbor_gap:
        typeof row.neighbor_gap === "number"
          ? normalizeScore01(row.neighbor_gap)
          : undefined,
    });
  }
  return { recognized_staff, unknown_faces };
}

export function parseVerifyPayload(
  data: unknown,
): FaceVerifyApiResponse | null {
  return parseFaceVerifyApiResponse(data);
}
