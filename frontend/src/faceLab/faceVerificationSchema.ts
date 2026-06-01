import { z } from "zod";

export const faceVerifyStatusSchema = z.enum([
  "VERIFIED",
  "REJECTED",
  "QUALITY_FAIL",
  "LIVENESS_FAIL",
  "PAD_ERROR",
]);

export type FaceVerifyStatus = z.infer<typeof faceVerifyStatusSchema>;

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

const padLivenessDiagnosticsSchema = z
  .object({
    diagnostics_version: z.string().optional(),
    decision: z
      .object({
        final_decision: z.string().optional(),
        product_outcome: z.string().optional(),
        trust_confirmed: z.boolean().nullable().optional(),
        operator_action: z.string().optional(),
        operator_action_reason: z.string().optional(),
      })
      .passthrough()
      .optional(),
  })
  .passthrough()
  .optional();

const livenessSchema = z.object({
  checked: z.boolean(),
  decision: z.enum(["YES", "NO", "REVIEW"]).optional(),
  operator_action: z.string().optional(),
  trust_confirmed: z.boolean().nullable().optional(),
  status: z.string().nullable().optional(),
  risk_score: z.number().nullable().optional(),
  model_version: z.string().nullable().optional(),
  tags: z.array(z.string()).optional(),
  elapsed_ms: z.number().optional(),
  deepface_score: z.number().optional(),
  device_score: z.number().optional(),
  frame_score: z.number().optional(),
  quality_penalty: z.number().optional(),
  device_bg_score: z.number().optional(),
  frame_global_score: z.number().optional(),
  recapture_score: z.number().optional(),
  face_reflection_score: z.number().optional(),
  color_hist_score: z.number().optional(),
  diagnostics: padLivenessDiagnosticsSchema,
  note: z.string().optional(),
});

const gallerySchema = z.object({
  total_templates: z.number(),
  distinct_enrollment_sources: z.number(),
});

const diagnosticsSchema = z
  .object({
    mode_used: z.string().optional(),
    gallery_breakdown: z.record(z.number()).optional(),
    threshold_cold_start: z.number().optional(),
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
  decision_summary: z.string().optional(),
  status: faceVerifyStatusSchema,
  gallery_strength: z.enum(["strong", "weak"]),
  threshold_applied: z.number(),
  score: z.number(),
  max_cosine: z.number(),
  threshold_verified_strong: z.number(),
  threshold_verified_weak: z.number(),
  gallery_size: z.number(),
  reason_codes: z.array(z.string()),
  quality: qualitySchema,
  liveness: livenessSchema,
  gallery: gallerySchema,
  diagnostics: diagnosticsSchema,
});

export type FaceVerifyContract = z.infer<typeof faceVerifyContractSchema>;

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
