import {
  parseFaceVerifyApiResponse,
  type FaceVerifyApiResponse,
} from "./faceVerificationSchema";

export type { FaceVerifyApiResponse } from "./faceVerificationSchema";

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
};

export function livenessToPadTestResponse(
  l: FaceVerifyApiResponse["liveness"],
): PadTestResponse | null {
  if (!l.checked) return null;
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
  };
}

export type RecognizedStaffRow = {
  pin: string;
  name?: string;
  surname?: string;
  department?: string | null;
  similarity: number;
  bbox: number[];
};

export type UnknownFaceRow = {
  status: string;
  bbox: number[];
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
  return data as PadTestResponse;
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
    unknown_faces.push({ status: row.status, bbox: row.bbox as number[] });
  }
  return { recognized_staff, unknown_faces };
}

export function parseVerifyPayload(
  data: unknown,
): FaceVerifyApiResponse | null {
  return parseFaceVerifyApiResponse(data);
}
