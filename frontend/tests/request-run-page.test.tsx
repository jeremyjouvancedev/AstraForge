import { describe, expect, it } from "vitest";

import { buildRepositoryBaseUrl } from "@/features/requests/pages/request-run-page";

describe("buildRepositoryBaseUrl", () => {
  it("builds a GitHub URL from a slug", () => {
    expect(
      buildRepositoryBaseUrl({
        repository: "octo/repo",
        provider: "github",
        baseUrl: null,
      }),
    ).toBe("https://github.com/octo/repo");
  });

  it("uses provided GitLab base URLs", () => {
    expect(
      buildRepositoryBaseUrl({
        repository: "group/repo",
        provider: "gitlab",
        baseUrl: "https://gitlab.example.com",
      }),
    ).toBe("https://gitlab.example.com/group/repo");
  });

  it("accepts full https URLs without double prefixes", () => {
    expect(
      buildRepositoryBaseUrl({
        repository: "https://github.com/octo/repo.git",
        provider: "github",
        baseUrl: null,
      }),
    ).toBe("https://github.com/octo/repo");
  });

  it("accepts ssh repository URLs", () => {
    expect(
      buildRepositoryBaseUrl({
        repository: "git@github.com:octo/repo.git",
        provider: "github",
        baseUrl: null,
      }),
    ).toBe("https://github.com/octo/repo");
  });
});
