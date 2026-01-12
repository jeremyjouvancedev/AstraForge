const WORKSPACE_ROOT = "/workspace";
const DEFAULT_FILENAME = "upload.bin";

export function buildSandboxUploadPath(inputPath: string, fileName: string): string {
  const fallback =
    fileName.split(/[/\\]/).pop()?.trim() || DEFAULT_FILENAME;
  let relative = inputPath.trim().replace(/\\/g, "/");

  if (!relative) {
    relative = fallback;
  } else {
    if (relative.startsWith(`${WORKSPACE_ROOT}/`)) {
      relative = relative.slice(`${WORKSPACE_ROOT}/`.length);
    } else if (relative === WORKSPACE_ROOT) {
      relative = "";
    } else if (relative.startsWith("workspace/")) {
      relative = relative.slice("workspace/".length);
    } else if (relative === "workspace") {
      relative = "";
    } else if (relative.startsWith("/")) {
      relative = relative.replace(/^\/+/, "");
    }

    if (!relative) {
      relative = fallback;
    } else if (relative.endsWith("/")) {
      relative = `${relative}${fallback}`;
    }
  }

  const path = `${WORKSPACE_ROOT}/${relative}`.replace(/\/{2,}/g, "/");
  const segments = path.split("/").filter(Boolean);
  if (segments.includes("..")) {
    throw new Error("Upload path must stay within /workspace.");
  }
  return path;
}
