export type PadDiagnosticsDecision = {
  final_decision?: string;
  product_outcome?: string;
  trust_confirmed?: boolean | null;
  operator_action?: string;
  operator_action_reason?: string;
};

export type PadUiDecision = "YES" | "NO" | "REVIEW";

export type PadDiagnosticsPayload = {
  diagnostics_version?: string;
  decision?: PadDiagnosticsDecision;
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
  "pad_diagnostics_v4",
  "pad_diagnostics_v5",
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
