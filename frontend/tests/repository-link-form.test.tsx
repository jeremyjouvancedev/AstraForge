import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RepositoryLinkForm } from "@/features/repositories/components/repository-link-form";
import * as apiClient from "@/lib/api-client";

describe("RepositoryLinkForm", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("submits form data to create a repository link", async () => {
    const createRepositoryLinkSpy = vi.spyOn(apiClient, "createRepositoryLink").mockResolvedValue({
      id: "1",
      provider: "github",
      repository: "jeremyjouvancedev/ai-flow",
      base_url: undefined,
      token_preview: "***abcd",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    } as unknown as apiClient.RepositoryLink);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } }
    });

    render(
      <QueryClientProvider client={queryClient}>
        <RepositoryLinkForm />
      </QueryClientProvider>
    );

    fireEvent.change(screen.getByLabelText(/Repository/i), {
      target: { value: "jeremyjouvancedev/ai-flow" }
    });
    fireEvent.change(screen.getByLabelText(/Personal access token/i), {
      target: { value: "token-1234" }
    });

    fireEvent.click(screen.getByRole("button", { name: /link repository/i }));

    await waitFor(() => expect(createRepositoryLinkSpy).toHaveBeenCalled());

    const variables = createRepositoryLinkSpy.mock.calls[0][0];
    expect(variables).toMatchObject({
      repository: "jeremyjouvancedev/ai-flow",
      access_token: "token-1234"
    });
    expect(["gitlab", "github"]).toContain(variables.provider);
  });
});
