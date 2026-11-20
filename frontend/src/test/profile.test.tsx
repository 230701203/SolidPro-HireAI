import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import ProfileEditPage from "@/pages/applicant/ProfileEditPage";
import { api } from "@/services/api";

const profile = {
  candidate_id: 1, user_id: 3, full_name: "Dev Applicant", email: "dev@example.com", mobile: null, date_of_birth: null, address: null, city: "Chennai",
  state: null, country: null, linkedin_url: null, portfolio_url: null, github_url: null, highest_qualification: null, total_experience_years: null,
  education: [], experience: [], skills: [{ id: 1, name: "AutoCAD", kind: "technical" }], resumes: [], completion: 40, missing: ["Highest qualification"],
};

beforeEach(() => vi.restoreAllMocks());

describe("Applicant profile page", () => {
  it("renders with saved skills instead of crashing", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: profile });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><ToastProvider><ProfileEditPage /></ToastProvider></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("My profile")).toBeInTheDocument();
    expect(await screen.findByText("AutoCAD")).toBeInTheDocument();
  });
});
