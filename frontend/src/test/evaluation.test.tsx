import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import ResultDetailPage from "@/pages/results/ResultDetailPage";
import MyResultsPage from "@/pages/results/MyResultsPage";
import MyInterviewsPage from "@/pages/interviews/MyInterviewsPage";
import { api } from "@/services/api";
import type { EvalDetail, EvalItem, MyInterview, MyResult } from "@/types";

const mcq: EvalItem = {
  id: 1, question_id: 11, section: "mcq", position: 1, text: "Which keyword defines a function?", options: ["func", "def"], selected_index: 0, selected_text: "func", correct_index: 1, correct_text: "def",
  is_correct: false, unanswered: false, max_marks: 1, auto_marks: 0, final_marks: 0, overridden: false, needs_review: false, review_note: null, stt_status: "not_applicable", speech: null, recordings: [],
};
const rs = (over: Partial<EvalItem> = {}): EvalItem => ({
  id: 2, question_id: 12, section: "repeat_sentence", position: 1, text: "Please send the drawings.", options: null, selected_index: null, selected_text: null, correct_index: null, correct_text: null,
  is_correct: null, unanswered: false, max_marks: 2, auto_marks: null, final_marks: null, overridden: false, needs_review: true,
  review_note: "No speech could be recognised. Please listen to the recording and score it.", stt_status: "low_confidence",
  speech: { expected: "Please send the drawings.", recognized: "", confidence: null, accuracy: null, completeness: null, missing: [], substituted: [], near_matches: [], extra: [], order_differs: false, provider: "mock", is_mock: true, error: null },
  recordings: [{ id: 77, attempt_no: 1, is_final: true }], ...over,
});
const detail = (over: Partial<EvalDetail> = {}): EvalDetail => ({
  id: 5, application_id: 3, schedule_id: 9, candidate_name: "Jane Doe", opening_title: "Python Developer", test_date: "2026-11-20T10:00:00Z", status: "draft", total_marks: 3, total_obtained: 0, percentage: 0,
  unresolved: 1, released: false, application_status: "approved", candidate_email: "jane@example.com", assessment_title: "Python Developer assessment", assessment_is_mock: false, duration_minutes: 45,
  time_taken_seconds: 1200, summary: "Scored 0 of 3 marks (0.0%). Automatic summary from fixed rules, not written by AI.",
  sections: [{ kind: "mcq", title: "MCQ", obtained: 0, total: 1, correct: 0, incorrect: 1, unanswered: 0, unresolved: 0 }, { kind: "repeat_sentence", title: "Repeat the Sentence", obtained: 0, total: 2, correct: 0, incorrect: 0, unanswered: 0, unresolved: 1 }],
  groups: [{ kind: "mcq", title: "MCQ", items: [mcq] }, { kind: "repeat_sentence", title: "Repeat the Sentence", items: [rs()] }], overrides: [], comments: [],
  blockers: ["1 speaking item(s) still need a score: listen to the recording, then confirm the suggestion or enter a score."], can_edit: true, speech_provider: "mock", speech_is_mock: true,
  applicant_feedback: null, finalized_at: null, released_at: null, ...over,
});

function wrap(path: string, route: string, el: ReactElement) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}><ToastProvider><Routes><Route path={route} element={el} /></Routes></ToastProvider></MemoryRouter>
    </QueryClientProvider>,
  );
}
beforeEach(() => vi.restoreAllMocks());

describe("Result review page", () => {
  it("warns that mock speech-to-text cannot read audio and flags the item for a person", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: detail() });
    wrap("/results/5", "/results/:id", <ResultDetailPage />);
    expect(await screen.findByText(/MOCK speech-to-text\./)).toBeInTheDocument();
    expect(screen.getByText(/No speech could be recognised/)).toBeInTheDocument();
    expect(screen.getByText("Not scored")).toBeInTheDocument();
    expect(screen.getByLabelText(/Recording for question 1, take 1/)).toHaveAttribute("src", "/api/recordings/77/file");
    expect(screen.getByText(/never the accent/i)).toBeInTheDocument();
  });

  it("shows the staff-side correct answer but blocks approval while an item is unscored", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: detail() });
    wrap("/results/5", "/results/:id", <ResultDetailPage />);
    expect(await screen.findByText("Correct answer: def")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve evaluation" })).toBeDisabled();
    expect(screen.getByText(/still need a score/)).toBeInTheDocument();
  });

  it("requires a reason before saving a manual score, and sends marks and reason", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: detail() });
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} });
    wrap("/results/5", "/results/:id", <ResultDetailPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Enter score" }));
    const save = screen.getByRole("button", { name: "Save score" });
    expect(save).toBeDisabled();
    await userEvent.clear(screen.getByLabelText(/Marks/));
    await userEvent.type(screen.getByLabelText(/Marks/), "1.5");
    await userEvent.type(screen.getByLabelText(/Reason/), "Listened: repeated most words");
    await userEvent.click(save);
    await waitFor(() => expect(post).toHaveBeenCalledWith("/evaluations/5/items/2/override", { marks: 1.5, reason: "Listened: repeated most words" }));
  });

  it("offers a provisional score to confirm instead of auto-applying it", async () => {
    const item = rs({ auto_marks: 2, speech: { ...rs().speech!, recognized: "Please send the drawings.", confidence: 0.4, accuracy: 1, completeness: 1, is_mock: false }, review_note: "Low-confidence transcript: provisional." });
    vi.spyOn(api, "get").mockResolvedValue({ data: detail({ groups: [{ kind: "repeat_sentence", title: "Repeat the Sentence", items: [item] }] }) });
    wrap("/results/5", "/results/:id", <ResultDetailPage />);
    expect(await screen.findByRole("button", { name: "Confirm suggested 2" })).toBeInTheDocument();
    expect(screen.getByText("Confidence 40%")).toBeInTheDocument();
  });

  it("final evaluations show decisions and release, never edit controls; rejecting needs a reason", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: detail({ status: "final", can_edit: false, blockers: [], unresolved: 0, finalized_at: "2026-11-21T10:00:00Z" }) });
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} });
    wrap("/results/5", "/results/:id", <ResultDetailPage />);
    expect(await screen.findByRole("button", { name: "Release to applicant" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change score" })).not.toBeInTheDocument();
    expect(screen.getByText(/never shortlists or rejects anyone by itself/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    const dialog = await screen.findByRole("dialog");
    const confirm = () => within(dialog).getByRole("button", { name: "Reject" });
    expect(confirm()).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "Did not meet the role requirements");
    expect(confirm()).toBeEnabled();
    await userEvent.click(confirm());
    await waitFor(() => expect(post).toHaveBeenCalledWith("/applications/3/decision", { decision: "reject", reason: "Did not meet the role requirements" }));
  });
});

describe("Applicant views", () => {
  const result: MyResult = {
    id: 5, application_id: 3, opening_title: "Python Developer", assessment_title: "Python Developer assessment", test_date: "2026-11-20T10:00:00Z", released_at: "2026-11-22T10:00:00Z",
    total_marks: 10, total_obtained: 7.5, percentage: 75, sections: [{ kind: "mcq", title: "MCQ", obtained: 5, total: 6 }, { kind: "repeat_sentence", title: "Repeat the Sentence", obtained: 2.5, total: 4 }],
    time_taken_seconds: 1500, feedback: "Good effort. Work on speaking pace.",
  };
  it("shows released scores and feedback without answer keys, with the human-decision reminder", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: [result] });
    wrap("/my-results/5", "/my-results/:id", <MyResultsPage />);
    expect(await screen.findByText("75%")).toBeInTheDocument();
    expect(screen.getByText("Good effort. Work on speaking pace.")).toBeInTheDocument();
    expect(screen.getByText(/accent is not penalised/i)).toBeInTheDocument();
    expect(screen.getByText(/People at SolidPro make the decisions/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/correct answer/i);
  });
  it("explains that nothing is released yet", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: [] });
    wrap("/my-results", "/my-results", <MyResultsPage />);
    expect(await screen.findByText("No released results")).toBeInTheDocument();
  });
  it("lists interviews with the meeting link only when there is one", async () => {
    const list: MyInterview[] = [{ id: 1, opening_title: "Python Developer", interview_type: "technical", mode: "online", status: "scheduled", scheduled_start: "2026-12-01T09:00:00Z", duration_minutes: 45, meeting_link: "https://meet.example/abc", location: null, instructions: "Keep ID ready" },
      { id: 2, opening_title: "CAD Engineer", interview_type: "hr", mode: "online", status: "cancelled", scheduled_start: null, duration_minutes: 30, meeting_link: null, location: null, instructions: null }];
    vi.spyOn(api, "get").mockResolvedValue({ data: list });
    wrap("/my-interviews", "/my-interviews", <MyInterviewsPage />);
    expect(await screen.findByRole("link", { name: "Join the meeting" })).toHaveAttribute("href", "https://meet.example/abc");
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.getByText("Keep ID ready")).toBeInTheDocument();
  });
});
