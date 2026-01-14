import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { HomeRoute } from "@/app/router";

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: null,
    isAuthenticated: false,
    loading: false,
    authSettings: {
      require_approval: false,
      allow_all_users: true,
      waitlist_enabled: false,
      self_hosted: true,
      billing_enabled: false,
      supported_providers: []
    },
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    refreshAuthSettings: vi.fn()
  })
}));

describe("HomeRoute", () => {
  it("redirects to /app when self-hosted is enabled", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<HomeRoute />} />
          <Route path="/app" element={<div>App Shell</div>} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText("App Shell")).toBeTruthy();
  });
});
