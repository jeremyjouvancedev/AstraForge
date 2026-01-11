import { describe, expect, it } from "vitest";

import { parseDomainList } from "@/features/computer-use/pages/computer-use-page";

describe("parseDomainList", () => {
  it("splits and normalizes domains", () => {
    expect(
      parseDomainList("Example.com, api.EXAMPLE.com\nfoo.bar  ")
    ).toEqual(["example.com", "api.example.com", "foo.bar"]);
  });

  it("deduplicates entries and preserves wildcards", () => {
    expect(parseDomainList("*, example.com, EXAMPLE.com, *")).toEqual([
      "*",
      "example.com"
    ]);
  });
});
