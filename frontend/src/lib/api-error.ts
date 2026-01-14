export function extractApiErrorMessage(payload: unknown): string | null {
  if (!payload) return null;
  if (typeof payload === "string") {
    return payload;
  }
  if (Array.isArray(payload)) {
    for (const entry of payload) {
      const nested = extractApiErrorMessage(entry);
      if (nested) return nested;
    }
    return null;
  }
  if (typeof payload === "object") {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const data = payload as Record<string, any>;
    if (typeof data.detail === "string") {
      return data.detail;
    }
    for (const value of Object.values(data)) {
      if (typeof value === "string" && value.trim()) {
        return value;
      }
      if (Array.isArray(value)) {
        const nested = value.find((entry) => typeof entry === "string");
        if (typeof nested === "string" && nested.trim()) {
          return nested;
        }
      }
    }
  }
  return null;
}
