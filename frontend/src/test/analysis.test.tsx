import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import AnalysisPanel from "@/components/AnalysisPanel";
import { api } from "@/services/api";
import type { AnalysisOverview, AnalysisReport } from "@/types";

const report: AnalysisReport = {
  id: 1, application_id: 5, resume_id: 1, resume_version: 1, status: "completed", provider: "mock", model: "keyword-matcher-v1",
  prompt_version: "resume-analysis-v1", is_mock: true, ai_score: 62, effective_score: 62, error: null,
  requested_by_name: "Ada Admin", created_at: "2026-11-11T10:00:00Z", override_score: null, override_note: null, overridden_by_name: null, overridden_at: null,
  report: {
    match_score: 62, confidence: "low", summary: "[MOCK] Keyword match only.", matched_required_skills: ["Python"], missing_required_skills: ["C++"],
    matched_preferred_skills: [], experience_assessment: "", education_assessment: "", strengths: [], gaps: [], clarifications_to_verify: [], suggested_interview_topics: [],
  },
};
const overview = (over: Partial<AnalysisOverview> = {}): AnalysisOverview => ({
  ai: { provider: "mock", model: "keyword-matcher-v1", is_mock: true, configured: true }, notice: "Advisory only. Never approves or rejects.",
  can_run: true, latest: report, history: [], ...over,
});

function mount() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ToastProvider><AnalysisPanel applicationId="5" /></ToastProvider>
    </QueryClientProvider>,
  );
}
beforeEach(() => vi.restoreAllMocks());

describe("AnalysisPanel", () => {
  it("labels mock output clearly and shows the advisory notice", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: overview() });
    mount();
    expect(await screen.findByText(/MOCK mode/)).toBeInTheDocument();
    expect(screen.getByText(/Advisory only/)).toBeInTheDocument();
    expect(screen.getByLabelText("Match score 62 out of 100")).toBeInTheDocument();
    expect(screen.getByText("C++")).toBeInTheDocument();
  });

  it("hides run and override controls from reviewers without the analysis permission", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: overview({ can_run: false }) });
    mount();
    expect(await screen.findByText(/MOCK mode/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run again/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /override score/i })).not.toBeInTheDocument();
  });

  it("shows a retryable error for a failed run and blocks running without an API key", async () => {
    const failed = { ...report, status: "failed" as const, ai_score: null, effective_score: null, report: null, error: "The AI service is rate limited." };
    vi.spyOn(api, "get").mockResolvedValue({ data: overview({ latest: failed, ai: { provider: "anthropic", model: "m", is_mock: false, configured: false } }) });
    mount();
    expect(await screen.findByText(/analysis failed/i)).toBeInTheDocument();
    expect(screen.getByText(/no API key/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run again/i })).toBeDisabled();
  });

  it("renders nothing when the server denies access", async () => {
    vi.spyOn(api, "get").mockRejectedValue({ isAxiosError: true, response: { status: 403, data: {} } });
    mount();
    await vi.waitFor(() => expect(api.get).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/AI resume analysis/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
