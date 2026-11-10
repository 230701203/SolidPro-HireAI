import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/contexts/AuthContext";
import { ToastProvider } from "@/components/Toast";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import LoginPage from "@/pages/auth/LoginPage";
import RegisterPage from "@/pages/auth/RegisterPage";
import { api } from "@/services/api";
import type { User } from "@/types";

const baseUser: User = {
  id: 1, email: "a@b.com", full_name: "Ada Admin", mobile: null, role: "admin", status: "active",
  must_change_password: false, email_verified_at: null, last_login_at: null, created_at: "2026-01-01T00:00:00Z",
  permissions: [], department: null, designation: null,
};

function mount(ui: React.ReactNode, route = "/") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[route]}>
        <ToastProvider>
          <AuthProvider>{ui}</AuthProvider>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const unauthenticated = () => vi.spyOn(api, "get").mockRejectedValue({ isAxiosError: true, response: { status: 401, data: {} } });

beforeEach(() => vi.restoreAllMocks());

describe("route guards", () => {
  it("redirects anonymous users to the login page", async () => {
    unauthenticated();
    mount(
      <Routes>
        <Route path="/login" element={<div>login screen</div>} />
        <Route element={<ProtectedRoute />}><Route path="/secret" element={<div>secret</div>} /></Route>
      </Routes>,
      "/secret",
    );
    expect(await screen.findByText("login screen")).toBeInTheDocument();
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("keeps applicants out of admin-only routes", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: { ...baseUser, role: "applicant" } });
    mount(
      <Routes>
        <Route path="/dashboard" element={<div>dashboard</div>} />
        <Route element={<ProtectedRoute />}>
          <Route element={<ProtectedRoute roles={["admin"]} />}><Route path="/admin" element={<div>admin area</div>} /></Route>
        </Route>
      </Routes>,
      "/admin",
    );
    expect(await screen.findByText("dashboard")).toBeInTheDocument();
    expect(screen.queryByText("admin area")).not.toBeInTheDocument();
  });

  it("forces a password change before anything else", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: { ...baseUser, must_change_password: true } });
    mount(
      <Routes>
        <Route path="/change-password" element={<div>change password screen</div>} />
        <Route element={<ProtectedRoute />}><Route path="/dashboard" element={<div>dashboard</div>} /></Route>
      </Routes>,
      "/dashboard",
    );
    expect(await screen.findByText("change password screen")).toBeInTheDocument();
  });

  it("lets admins into admin routes", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: baseUser });
    mount(
      <Routes><Route element={<ProtectedRoute roles={["admin"]} />}><Route path="/admin" element={<div>admin area</div>} /></Route></Routes>,
      "/admin",
    );
    expect(await screen.findByText("admin area")).toBeInTheDocument();
  });
});

describe("login form", () => {
  it("validates before calling the API", async () => {
    unauthenticated();
    const post = vi.spyOn(api, "post");
    mount(<LoginPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your email")).toBeInTheDocument();
    expect(screen.getByText("Enter your password")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("shows the server's reason when approval is pending", async () => {
    unauthenticated();
    vi.spyOn(api, "post").mockRejectedValue({
      isAxiosError: true,
      response: { status: 403, data: { error: { code: "pending_approval", message: "Your registration is waiting for administrator approval." } } },
    });
    mount(<LoginPage />);
    await userEvent.type(await screen.findByLabelText("Email address"), "emp@solidpro.example");
    await userEvent.type(screen.getByLabelText("Password"), "whatever123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText(/waiting for administrator approval/)).toBeInTheDocument();
  });

  it("toggles password visibility", async () => {
    unauthenticated();
    mount(<LoginPage />);
    const input = await screen.findByLabelText("Password");
    expect(input).toHaveAttribute("type", "password");
    await userEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(input).toHaveAttribute("type", "text");
  });
});

describe("registration form", () => {
  it("enforces password rules, confirmation and consent client-side", async () => {
    unauthenticated();
    const post = vi.spyOn(api, "post");
    mount(<RegisterPage />);
    await userEvent.type(await screen.findByLabelText("Full name"), "Jane Doe");
    await userEvent.type(screen.getByLabelText("Email address"), "jane@gmail.com");
    await userEvent.type(screen.getByLabelText("Password"), "short");
    await userEvent.type(screen.getByLabelText("Confirm password"), "different");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("At least 10 characters")).toBeInTheDocument();
    expect(screen.getByText("Passwords do not match")).toBeInTheDocument();
    expect(screen.getByText("You must accept the privacy notice")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("submits valid data and shows the check-your-email screen", async () => {
    unauthenticated();
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { message: "Check your inbox for a verification link to activate your account." } });
    mount(<RegisterPage />);
    await userEvent.type(await screen.findByLabelText("Full name"), "Jane Doe");
    await userEvent.type(screen.getByLabelText("Email address"), "jane@gmail.com");
    await userEvent.type(screen.getByLabelText("Mobile number"), "+919876543210");
    await userEvent.type(screen.getByLabelText("Password"), "Str0ngPassw0rd!");
    await userEvent.type(screen.getByLabelText("Confirm password"), "Str0ngPassw0rd!");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][1]).toMatchObject({ email: "jane@gmail.com", accept_terms: true, mobile: "+919876543210" });
    expect(await screen.findByText(/verification link/)).toBeInTheDocument();
  });
});
