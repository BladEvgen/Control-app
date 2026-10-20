export type PadUiDecision = "YES" | "NO";

export function padDecisionOf(
  decision: unknown,
  status?: string | null,
): PadUiDecision {
  if (decision === "YES" || decision === "NO") return decision;
  return (status ?? "").trim() === "clean" ? "YES" : "NO";
}
