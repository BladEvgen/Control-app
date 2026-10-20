import {
  parseFaceVerifyApiResponse,
  type FaceVerifyApiResponse,
} from "./faceVerificationSchema";
import { padDecisionOf, type PadUiDecision } from "./faceLabPadTypes";

export type { FaceVerifyApiResponse } from "./faceVerificationSchema";

export type PadTestResponse = {
  decision: PadUiDecision;
  status: string;
};

export type RecognizedStaffRow = {
  pin: string;
  name?: string;
  surname?: string;
  department?: string | null;
  similarity: number;
  neighbor_gap?: number;
  bbox: number[];
  avatar_url?: string | null;
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
  if (!isRecord(data) || typeof data.status !== "string") return null;
  return {
    decision: padDecisionOf(data.decision, data.status),
    status: data.status,
  };
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
      avatar_url:
        row.avatar_url === null || typeof row.avatar_url === "string"
          ? (row.avatar_url as string | null)
          : undefined,
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
