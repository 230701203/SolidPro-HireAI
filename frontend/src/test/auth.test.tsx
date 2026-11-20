import { render, screen, waitFor, within } from "@testing-library/react";
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

  it("checks the email live but never shows password-policy rules on sign-in", async () => {
    unauthenticated();
    mount(<LoginPage />);
    const email = await screen.findByLabelText("Email address");
    await userEvent.type(email, "admin@solidpro");
    expect(await screen.findByText(/must look like company.com/)).toBeInTheDocument();
    await userEvent.type(email, ".example");
    expect(await screen.findByText("Email format looks good")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Password"), "oldpass");
    expect(screen.queryByTestId("password-checklist")).not.toBeInTheDocument();
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
    expect(await screen.findByText(/Password needs: 10 to 64 characters/)).toBeInTheDocument();
    expect(screen.getByText("Passwords do not match")).toBeInTheDocument();
    expect(screen.getByText("You must accept the privacy notice")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("shows live feedback: rules tick off as you type, with a strength label", async () => {
    unauthenticated();
    mount(<RegisterPage />);
    const pw = await screen.findByLabelText("Password");
    const list = screen.getByTestId("password-checklist");
    const status = (label: RegExp) => within(list).getByText(label).closest("li")!.textContent;
    await userEvent.type(pw, "abc");
    expect(status(/lowercase letter/)).toMatch(/\(met\)/);
    expect(status(/uppercase letter/)).toMatch(/\(not met\)/);
    expect(within(list).getByText(/Strength: Weak/)).toBeInTheDocument();
    await userEvent.type(pw, "DEF1");
    expect(status(/uppercase letter/)).toMatch(/\(met\)/);
    expect(status(/A number/)).toMatch(/\(met\)/);
    expect(status(/A symbol/)).toMatch(/\(not met\)/);
    await userEvent.type(pw, "!ghijk");
    expect(status(/A symbol/)).toMatch(/\(met\)/);
    expect(status(/10 to 64 characters/)).toMatch(/\(met\)/);
    expect(within(list).getByText(/Strength: (Good|Strong)/)).toBeInTheDocument();
    expect(screen.getByText("13 / 64")).toBeInTheDocument();
    await userEvent.type(pw, "password");
    expect(status(/No common words/)).toMatch(/\(not met\)/);
    await userEvent.type(screen.getByLabelText("Confirm password"), "abcDEF1!ghijkpassword");
    expect(await screen.findByText("Passwords match")).toBeInTheDocument();
  });

  it("gives live feedback on name and email, with a character counter", async () => {
    unauthenticated();
    mount(<RegisterPage />);
    const name = await screen.findByLabelText("Full name");
    await userEvent.type(name, "Jane3");
    expect(await screen.findByText(/Use letters, spaces and/)).toBeInTheDocument();
    await userEvent.clear(name);
    await userEvent.type(name, "Jane Doe");
    expect(await screen.findAllByText("Looks good")).not.toHaveLength(0);
    expect(screen.getByText("8 / 60")).toBeInTheDocument();
    const email = screen.getByLabelText("Email address");
    await userEvent.type(email, "12345@gmail.com");
    expect(await screen.findByText(/must contain at least one letter/)).toBeInTheDocument();
    await userEvent.clear(email);
    await userEvent.type(email, "jane@gmail");
    expect(await screen.findByText(/must look like company.com/)).toBeInTheDocument();
    await userEvent.type(email, ".com");
    expect(await screen.findByText("Email format looks good")).toBeInTheDocument();
  });

  it("stops typing beyond the limits", async () => {
    unauthenticated();
    mount(<RegisterPage />);
    const name = (await screen.findByLabelText("Full name")) as HTMLInputElement;
    await userEvent.type(name, "A".repeat(80));
    expect(name.value).toHaveLength(60);
    const pw = screen.getByLabelText("Password") as HTMLInputElement;
    await userEvent.type(pw, "a".repeat(80));
    expect(pw.value).toHaveLength(64);
  });

  it("rejects a password containing the email name", async () => {
    unauthenticated();
    mount(<RegisterPage />);
    await userEvent.type(await screen.findByLabelText("Email address"), "priya.raman@gmail.com");
    await userEvent.type(screen.getByLabelText("Password"), "Priya.raman#2026X");
    const item = within(screen.getByTestId("password-checklist")).getByText(/Does not contain your email name/).closest("li")!;
    expect(item.textContent).toMatch(/\(not met\)/);
  });

  it("refuses a 9-digit Indian mobile number with a live message and ignores non-digits", async () => {
    unauthenticated();
    mount(<RegisterPage />);
    const box = await screen.findByLabelText("Mobile number");
    await userEvent.type(box, "98765-4321ab");
    expect(box).toHaveValue("987654321");
    expect(await screen.findByText(/exactly 10 digits \(you entered 9\)/)).toBeInTheDocument();
    await userEvent.type(box, "0");
    await waitFor(() => expect(screen.queryByText(/exactly 10 digits/)).not.toBeInTheDocument());
  });

  it("submits valid data and shows the check-your-email screen", async () => {
    unauthenticated();
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { message: "Check your inbox for a verification link to activate your account." } });
    mount(<RegisterPage />);
    await userEvent.type(await screen.findByLabelText("Full name"), "Jane Doe");
    await userEvent.type(screen.getByLabelText("Email address"), "jane@gmail.com");
    await userEvent.type(screen.getByLabelText("Mobile number"), "9876543210");
    await userEvent.type(screen.getByLabelText("Password"), "Str0ngPassw0rd!");
    await userEvent.type(screen.getByLabelText("Confirm password"), "Str0ngPassw0rd!");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][1]).toMatchObject({ email: "jane@gmail.com", accept_terms: true, mobile: "+91 9876543210" });
    expect(await screen.findByText(/verification link/)).toBeInTheDocument();
  });
});
