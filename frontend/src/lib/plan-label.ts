export function formatPlanLabel(plan?: string | null): string | null {
  if (!plan) return null;
  return plan
    .split("_")
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}
