import { describe, expect, it } from "vitest";

import { buildSandboxUploadPath } from "@/features/deepagent/lib/sandbox-upload";

describe("buildSandboxUploadPath", () => {
  it("defaults to /workspace with the file name", () => {
    expect(buildSandboxUploadPath("", "notes.txt")).toBe("/workspace/notes.txt");
  });

  it("appends the file name for directory paths", () => {
    expect(buildSandboxUploadPath("assets/", "image.png")).toBe("/workspace/assets/image.png");
  });

  it("accepts workspace-prefixed paths", () => {
    expect(buildSandboxUploadPath("/workspace/report.csv", "ignored.csv")).toBe(
      "/workspace/report.csv"
    );
  });

  it("treats bare workspace as the root", () => {
    expect(buildSandboxUploadPath("workspace", "script.py")).toBe("/workspace/script.py");
  });

  it("re-roots absolute paths into /workspace", () => {
    expect(buildSandboxUploadPath("/tmp/output.log", "output.log")).toBe(
      "/workspace/tmp/output.log"
    );
  });

  it("rejects traversal outside /workspace", () => {
    expect(() => buildSandboxUploadPath("../secrets.txt", "secrets.txt")).toThrow(
      "Upload path must stay within /workspace."
    );
  });
});
