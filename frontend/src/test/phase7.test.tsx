import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import BulkBatchDetailPage from "@/pages/bulk/BulkBatchDetailPage";
import BulkBatchesPage from "@/pages/bulk/BulkBatchesPage";
import AnalyticsPage from "@/pages/analytics/AnalyticsPage";
import ComparePage from "@/pages/analytics/ComparePage";
import { api } from "@/services/api";
import type { Analytics, BulkBatch, BulkItem } from "@/types";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { role: "admin", permissions: [] }, hasPermission: () => true }) }));

const progress = { queued: 0, processing: 0, done: 2, failed: 0, total: 2, finished: 2, complete: true };
const batch: BulkBatch = { id: 4, name: "Campus drive", opening_id: 1, opening_title: "Python Developer", created_by_name: "Admin", created_at: "2026-11-14T10:00:00Z", ai_provider: "mock", ai_is_mock: true, progress };
const item = (over: Partial<BulkItem> = {}): BulkItem => ({
  id: 1, filename: "a.pdf", size_bytes: 1000, status: "done", error: null, attempts: 1, candidate_name: "Priya Raman", email: "priya@example.org", phone: null, skills: ["Python"], experience_years: 4,
  match_score: 80, duplicate_kind: null, duplicate_of_item_id: null, existing_applicant: false, existing_application_id: null, review_status: "unreviewed", review_note: null, warnings: [], ...over,
});
const page = <T,>(items: T[]) => ({ items, total: items.length, page: 1, page_size: 20, pages: 1 });

function wrap(path: string, route: string, el: ReactElement) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}><ToastProvider><Routes><Route path={route} element={el} /></Routes></ToastProvider></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.restoreAllMocks());

describe("bulk screening", () => {
  it("lists batches and labels mock AI", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: page([batch]) });
    wrap("/bulk", "/bulk", <BulkBatchesPage />);
    expect(await screen.findByText("Campus drive")).toBeInTheDocument();
    expect(screen.getByText("MOCK AI")).toBeInTheDocument();
    expect(screen.getByText(/Complete · 2\/2/)).toBeInTheDocument();
  });

  it("shows ranked items, duplicate flags, an advisory notice, and saves a triage label", async () => {
    const put = vi.spyOn(api, "put").mockResolvedValue({ data: item() });
    vi.spyOn(api, "get").mockImplementation(async (url: string) => {
      if (url.endsWith("/items")) return { data: page([item(), item({ id: 2, candidate_name: "Karan Shah", match_score: 40, duplicate_kind: "existing_applicant", existing_applicant: true, existing_application_id: 9 })]) };
      return { data: batch };
    });
    wrap("/bulk/4", "/bulk/:id", <BulkBatchDetailPage />);
    expect(await screen.findByText("Priya Raman")).toBeInTheDocument();
    expect(screen.getByText(/MOCK AI: scores come from a simple keyword matcher/)).toBeInTheDocument();
    expect(screen.getByText("Registered applicant")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open their application/ })).toHaveAttribute("href", "/applications/9");
    await userEvent.selectOptions(screen.getByLabelText("Triage for Priya Raman"), "interesting");
    await waitFor(() => expect(put).toHaveBeenCalledWith("/bulk-items/1/triage", { status: "interesting" }));
  });

  it("offers a retry button only when files failed", async () => {
    vi.spyOn(api, "get").mockImplementation(async (url: string) => (url.endsWith("/items") ? { data: page([item({ status: "failed", match_score: null, error: "bad" })]) } : { data: { ...batch, progress: { ...progress, done: 1, failed: 1 } } }));
    wrap("/bulk/4", "/bulk/:id", <BulkBatchDetailPage />);
    expect(await screen.findByRole("button", { name: /Retry 1 failed/ })).toBeInTheDocument();
  });
});

const analytics: Analytics = {
  totals: { applications: 3, pending: 1, approved: 1, rejected: 1, withdrawn: 0, shortlisted: 1, selected: 0, openings_in_scope: 2, decided: 2 },
  rates: { approval_rate: 50, rejection_rate: 50, completion_rate: 100, attendance_rate: null, shortlisting_rate: 100, selection_rate: 0 },
  denominators: { decided: 2, scheduled: 1, attended_or_missed: 0, evaluated: 1, shortlisted: 1 },
  status_distribution: [], funnel: [{ stage: "Applied", count: 3 }], per_opening: [{ id: 1, name: "Python Developer", applications: 3, approved: 1, rejected: 1, shortlisted: 1, selected: 0 }], per_category: [],
  applications_by_month: [{ month: "2026-11", count: 3 }], scores: { evaluated_candidates: 1, average_percentage: 72, distribution: [], performance_trend: [] },
  match_scores: { analysed: 1, average: 60, trend: [], top_matched_skills: [], top_missing_skills: [{ skill: "Docker", count: 1 }] },
  stage_durations: [{ stage: "Applied → approved", avg_days: 1.5, sample: 1 }], notes: ["Pending = submitted, under review or info requested."], generated_at: "2026-11-14T10:00:00Z",
};

describe("analytics", () => {
  it("shows real figures with denominators, n/a for undefined rates, and export links", async () => {
    vi.spyOn(api, "get").mockImplementation(async (url: string) => (url.includes("analytics") ? { data: analytics } : url.includes("categories") ? { data: [] } : { data: page([]) }));
    wrap("/analytics", "/analytics", <AnalyticsPage />);
    expect(await screen.findByText("Pending review")).toBeInTheDocument();
    expect(screen.getAllByText("of 2 decided").length).toBe(2);
    expect(screen.getByText("n/a")).toBeInTheDocument(); // attendance: no denominator, no invented number
    expect(screen.getByText("Docker")).toBeInTheDocument();
    expect(screen.getByText(/How these are calculated/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "CSV" })[0]).toHaveAttribute("href", expect.stringContaining("/api/analytics/export?report=openings&format=csv"));
  });

  it("shows an empty state when nothing matches", async () => {
    vi.spyOn(api, "get").mockImplementation(async (url: string) => (url.includes("analytics") ? { data: { ...analytics, totals: { ...analytics.totals, applications: 0 } } } : url.includes("categories") ? { data: [] } : { data: page([]) }));
    wrap("/analytics", "/analytics", <AnalyticsPage />);
    expect(await screen.findByText("No applications match")).toBeInTheDocument();
  });

  it("compare needs 2-5 selections and renders mock-labelled scores side by side", async () => {
    wrap("/analytics/compare?ids=1", "/analytics/compare", <ComparePage />);
    expect(await screen.findByText(/Choose between 2 and 5 results/)).toBeInTheDocument();
  });

  it("compare renders candidates", async () => {
    const row = (id: number, name: string, score: number) => ({ application_id: id, candidate_name: name, opening_title: "Python Developer", status: "approved", experience_years: 2, match_score: score, match_is_mock: true, matched_required_skills: ["Python"], missing_required_skills: [], evaluation_percentage: 70, sections: [{ section: "mcq", obtained: 3, total: 5 }] });
    vi.spyOn(api, "get").mockResolvedValue({ data: [row(1, "Jane Doe", 80), row(2, "Sam Roe", 55)] });
    wrap("/analytics/compare?ids=1,2", "/analytics/compare", <ComparePage />);
    expect(await screen.findByText("Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("Sam Roe")).toBeInTheDocument();
    expect(screen.getAllByText("MOCK").length).toBe(2);
  });
});
