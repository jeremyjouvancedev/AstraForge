import { describe, expect, it } from "vitest";

import { cn } from "@/lib/cn";

describe("cn helper", () => {
  it("merges class names without duplicates", () => {
    expect(cn("p-4", "p-4", { "text-sm": true })).toBe("p-4 text-sm");
  });
});
