import { z } from "zod";

export const faceVerifyStatusSchema = z.enum([
  "VERIFIED",
  "REJECTED",
  "QUALITY_FAIL",
  "LIVENESS_FAIL",
  "PAD_ERROR",
]);

const qualitySchema = z.object({
  passed: z.boolean(),
  det_score: z.number().nullable().optional(),
  face_area_ratio: z.number().nullable().optional(),
  blur_laplacian_var: z.number().nullable().optional(),
  brightness_mean: z.number().nullable().optional(),
  pose_yaw: z.number().nullable().optional(),
  pose_pitch: z.number().nullable().optional(),
  pose_roll: z.number().nullable().optional(),
  reason_codes: z.array(z.string()).optional(),
});

const livenessSchema = z.object({
  checked: z.boolean(),
  decision: z.enum(["YES", "NO"]).optional(),
  status: z.string().nullable().optional(),
  risk_score: z.number().nullable().optional(),
  model_version: z.string().nullable().optional(),
  tags: z.array(z.string()).optional(),
  elapsed_ms: z.number().optional(),
});

const diagnosticsSchema = z
  .object({
    mode_used: z.string().optional(),
    gallery_breakdown: z.record(z.number()).optional(),
    identity_margin: z
      .object({
        impostor_guard_checked: z.boolean().optional(),
        nearest_impostor_pin: z.string().nullable().optional(),
        nearest_impostor_similarity: z.number().optional(),
        impostor_gap: z.number().optional(),
        impostor_gap_min: z.number().optional(),
        impostor_min_other_score: z.number().optional(),
        impostor_ambiguous: z.boolean().optional(),
        impostor_guard_disabled: z.boolean().optional(),
        impostor_guard_note: z.string().optional(),
        impostor_guard_error: z.string().optional(),
      })
      .passthrough()
      .optional(),
  })
  .passthrough()
  .optional();

export const faceVerifyContractSchema = z.object({
  matched: z.boolean(),
  final_decision: z.enum(["YES", "NO"]),
  summary: z.string(),
  status: faceVerifyStatusSchema,
  threshold_applied: z.number(),
  score: z.number(),
  max_cosine: z.number(),
  gallery_size: z.number(),
  reason_codes: z.array(z.string()),
  quality: qualitySchema,
  liveness: livenessSchema,
  diagnostics: diagnosticsSchema,
});

export const faceVerifyApiResponseSchema = faceVerifyContractSchema.extend({
  face_parsing_active: z.boolean().optional(),
  probe_eyeglasses_likely: z.boolean().nullable().optional(),
  probe_eyeglasses_area_frac: z.number().nullable().optional(),
  face_parsing_error: z.string().optional(),
});

export type FaceVerifyApiResponse = z.infer<typeof faceVerifyApiResponseSchema>;

export function parseFaceVerifyApiResponse(
  data: unknown,
): FaceVerifyApiResponse | null {
  const r = faceVerifyApiResponseSchema.safeParse(data);
  return r.success ? r.data : null;
}
