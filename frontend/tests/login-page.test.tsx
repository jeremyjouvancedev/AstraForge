import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "@/features/auth/pages/login-page";

let authSettings = {
  require_approval: false,
  allow_all_users: false,
  waitlist_enabled: true,
  self_hosted: false,
  billing_enabled: false,
  supported_providers: []
};

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: null,
    isAuthenticated: false,
    loading: false,
    authSettings,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    refreshAuthSettings: vi.fn()
  })
}));

describe("LoginPage", () => {
  beforeEach(() => {
    authSettings = {
      require_approval: false,
      allow_all_users: false,
      waitlist_enabled: true,
      self_hosted: false,
      billing_enabled: false,
      supported_providers: []
    };
  });

  it("shows the gated access alert when waitlist is enabled for hosted mode", () => {
    authSettings = {
      require_approval: false,
      allow_all_users: false,
      waitlist_enabled: true,
      self_hosted: false,
      billing_enabled: true,
      supported_providers: []
    };

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    expect(screen.getByText("Access is gated")).toBeTruthy();
  });

  it("hides the gated access alert when self-hosted", () => {
    authSettings = {
      require_approval: false,
      allow_all_users: false,
      waitlist_enabled: true,
      self_hosted: true,
      billing_enabled: false,
      supported_providers: []
    };

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    expect(screen.queryByText("Access is gated")).toBeNull();
  });
});
