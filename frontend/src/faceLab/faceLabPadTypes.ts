export type PadDiagnosticsDecision = {
  final_decision?: string;
  product_outcome?: string;
  trust_confirmed?: boolean | null;
  decision_branch?: string | null;
  decision_source?: string;
  presentation_confidence?: number;
};

export type PadDiagnosticsPresentation = {
  spoof_risk?: number;
  fake_signal_score?: number;
  face_device_score?: number;
  face_frame_score?: number;
  recapture_score?: number;
};

export type PadDiagnosticsQuality = {
  overall_penalty?: number;
  face_area_ratio?: number;
  quality_flags?: string[];
  is_degraded?: boolean;
};

export type PadDiagnosticsBackground = {
  background_device_score?: number;
  background_frame_score?: number;
  context_codes?: string[];
};

export type PadDiagnosticsUncertainty = {
  uncertainty_codes?: string[];
  review_reason_codes?: string[];
  clean_reason_codes?: string[];
  interpretability_codes?: string[];
  conflicting_signal_codes?: string[];
  missing_signal_codes?: string[];
};

export type PadDiagnosticsTrace = {
  pad_trace_schema?: string | null;
  rule_codes?: string[];
  evidence_codes?: string[];
  evidence_metrics?: Record<string, number>;
  decision_support_flags?: string[];
};

export type PadDiagnosticsPayload = {
  diagnostics_version?: string;
  decision?: PadDiagnosticsDecision;
  presentation?: PadDiagnosticsPresentation;
  quality?: PadDiagnosticsQuality;
  background_context?: PadDiagnosticsBackground;
  uncertainty?: PadDiagnosticsUncertainty;
  trace?: PadDiagnosticsTrace;
  operator_tags?: string[];
  model_version?: string;
  elapsed_ms?: number;
};

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null;
}

export function isPlainObject(x: unknown): x is Record<string, unknown> {
  return isRecord(x) && !Array.isArray(x);
}

const SUPPORTED_DIAGNOSTICS_VERSIONS = new Set([
  "pad_diagnostics_v2",
  "pad_diagnostics_v3",
]);

export function coercePadDiagnostics(
  raw: unknown,
): PadDiagnosticsPayload | null {
  if (!isRecord(raw)) return null;
  if (
    typeof raw.diagnostics_version !== "string" ||
    !SUPPORTED_DIAGNOSTICS_VERSIONS.has(raw.diagnostics_version)
  ) {
    return null;
  }
  return raw as PadDiagnosticsPayload;
}
