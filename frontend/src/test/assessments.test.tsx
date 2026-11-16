import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import QuestionEditor, { emptyDraft, validateDraft } from "@/components/QuestionEditor";
import AssessmentDetailPage from "@/pages/assessments/AssessmentDetailPage";
import { api } from "@/services/api";
import type { AQuestion, AssessmentDetail } from "@/types";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ hasPermission: () => false }) }));

const q = (over: Partial<AQuestion>): AQuestion => ({
  id: 1, section: "mcq", position: 1, status: "pending", source: "template", text: "What does the expression evaluate to?", options: ["a", "b", "c", "d"], correct_index: 1,
  explanation: "Because b.", difficulty: "easy", topic: "Core", skill: "Python", q_type: "technical", marks: 1, edited: false, is_placeholder: false,
  reviewed_by_name: null, reviewed_at: null, reject_reason: null, ...over,
});

const detail = (over: Partial<AssessmentDetail> = {}): AssessmentDetail => ({
  id: 7, application_id: 3, candidate_name: "Jane Doe", opening_title: "Python Developer", title: "Python Developer assessment", status: "draft", difficulty: "medium",
  duration_minutes: 45, config: { rs_record_seconds: 20, rs_max_replays: 1, rs_max_attempts: 1 }, ai: { provider: "mock", model: "keyword-matcher-v1", is_mock: true, prompt_version: "assessment-generation-v1" },
  created_by_name: "Ada Admin", created_at: "2026-11-11T10:00:00Z", updated_at: "2026-11-11T10:00:00Z", total_marks: 1,
  sections: [
    { id: 1, kind: "mcq", title: "MCQ", total_marks: 1, questions: [q({}), q({ id: 2, position: 2, is_placeholder: true, text: "[MOCK PLACEHOLDER] Write a question" })] },
    { id: 2, kind: "aptitude", title: "Aptitude", total_marks: 0, questions: [] },
    { id: 3, kind: "repeat_sentence", title: "Repeat the Sentence", total_marks: 0, questions: [] },
  ],
  counts: { total: 2, approved: 0, pending: 2, rejected: 0 }, blockers: ["The Aptitude section has no questions.", "2 question(s) still need to be approved or rejected."],
  has_unapproved_changes: false, latest_version: null, published_version: null, versions: [], approvals: [], generation_notes: ["MOCK mode: x", "Only 1 of 3 MCQ questions could be generated."],
  can_edit: true, can_generate: true, notice: "Questions are drafts until a person approves them.", ...over,
});

function mount(d: AssessmentDetail) {
  vi.spyOn(api, "get").mockResolvedValue({ data: d });
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/assessments/7"]}>
        <ToastProvider><Routes><Route path="/assessments/:id" element={<AssessmentDetailPage />} /></Routes></ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
beforeEach(() => vi.restoreAllMocks());

describe("QuestionEditor validation", () => {
  it("rejects duplicate options and out-of-range answers", () => {
    const d = { ...emptyDraft("mcq"), text: "A real question?", options: ["A", "a", "C", "D"] };
    expect(validateDraft(d)).toMatch(/different/);
    expect(validateDraft({ ...d, options: ["A", "B", "C", "D"] })).toBeNull();
    expect(validateDraft({ ...d, options: ["A", "B", "", "D"] })).toMatch(/Fill in/);
  });
  it("checks the sentence length for Repeat the Sentence", () => {
    expect(validateDraft({ ...emptyDraft("repeat_sentence"), text: "Too short." })).toMatch(/5 to 30/);
    expect(validateDraft({ ...emptyDraft("repeat_sentence"), text: "Please send the revised drawing to the team." })).toBeNull();
  });
  it("disables Save until the draft is valid and shows no options for sentences", async () => {
    const onSave = vi.fn();
    render(<QuestionEditor title="Write a question" initial={emptyDraft("repeat_sentence")} saving={false} error={null} onSave={onSave} onClose={() => {}} />);
    expect(screen.queryByText(/Answer options/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Sentence the applicant will hear/), "Please send the revised drawing to the team.");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });
});

describe("AssessmentDetailPage", () => {
  it("labels mock content, lists what blocks approval and keeps Approve disabled", async () => {
    mount(detail());
    expect(await screen.findByText(/MOCK mode\./)).toBeInTheDocument();
    expect(screen.getByText("The Aptitude section has no questions.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve assessment" })).toBeDisabled();
    expect(screen.getByText(/Only 1 of 3 MCQ/)).toBeInTheDocument();
    expect(screen.getAllByText("Correct answer").length).toBeGreaterThan(0);
  });
  it("offers no Approve button on a placeholder question", async () => {
    mount(detail());
    await screen.findByText(/Placeholder\./);
    expect(screen.getAllByRole("button", { name: /^Approve$/ })).toHaveLength(1); // only the real question
  });
  it("hides every editing control from a read-only viewer", async () => {
    mount(detail({ can_edit: false, can_generate: false }));
    await screen.findByText(/MOCK mode\./);
    expect(screen.queryByRole("button", { name: "Approve assessment" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Edit/ })).not.toBeInTheDocument();
    expect(screen.getByText(/needs the “approve assessments” permission/)).toBeInTheDocument();
  });
  it("explains that an approved version stays in force while changes are pending", async () => {
    mount(detail({ status: "draft", latest_version: 1, has_unapproved_changes: true, versions: [{ id: 1, version: 1, total_marks: 5, duration_minutes: 45, content_hash: "a".repeat(64), approved_by_name: "Ada", approved_at: "2026-11-11T10:00:00Z", published_at: null, published_by_name: null }] }));
    expect(await screen.findByText(/The approved version is unchanged/)).toBeInTheDocument();
    expect(screen.getByText("Draft (changes since v1)")).toBeInTheDocument();
  });
});
