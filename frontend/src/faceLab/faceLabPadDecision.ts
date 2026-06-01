import type { PadDiagnosticsPayload, PadUiDecision } from "./faceLabPadTypes";

export function padUiDecisionFromDiagnostics(
  diagnostics: PadDiagnosticsPayload | null,
): PadUiDecision {
  const d = diagnostics?.decision;
  const action = d?.operator_action?.trim();
  const finalDecision = d?.final_decision?.trim();
  const trust = d?.trust_confirmed;

  if (
    action === "reject" ||
    finalDecision === "suspicious" ||
    trust === false
  ) {
    return "NO";
  }
  if (action === "manual_review" || action === "retry_photo") {
    return "REVIEW";
  }
  if (
    action === "accept" ||
    action === "accept_with_caution" ||
    finalDecision === "clean" ||
    trust === true
  ) {
    return "YES";
  }
  return "REVIEW";
}

export function padUiDecisionFromRaw(
  status?: string | null,
  trust?: boolean | null,
): PadUiDecision {
  const s = (status ?? "").trim();
  if (trust === false || s === "suspicious") return "NO";
  if (trust === true || s === "clean") return "YES";
  return "REVIEW";
}
