import type { ReactElement } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import MyTestDetailPage from "@/pages/tests/MyTestDetailPage";
import TestRunnerPage from "@/pages/tests/TestRunnerPage";
import { api } from "@/services/api";
import type { Invitation, TakeAttempt } from "@/types";

const inv = (over: Partial<Invitation> = {}): Invitation => ({
  id: 5, application_id: 3, opening_title: "Python Developer", assessment_title: "Python Developer assessment", status: "accepted",
  window_start: "2026-11-20T09:00:00Z", window_end: "2026-11-21T09:00:00Z", duration_minutes: 45, instructions: null, link_expires_at: "2026-11-21T09:00:00Z",
  sections: [{ kind: "mcq", title: "MCQ", questions: 3 }, { kind: "repeat_sentence", title: "Repeat the Sentence", questions: 2 }], has_repeat_sentence: true,
  rs_max_replays: 1, rs_max_attempts: 1, rs_record_seconds: 20, can_accept: false, can_start: true, start_blocked_reason: null, can_request_reschedule: true,
  attempt_id: null, reschedules: [], server_now: "2026-11-20T10:00:00Z", ...over,
});

function wrap(path: string, route: string, el: ReactElement) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}><ToastProvider><Routes><Route path={route} element={el} /></Routes></ToastProvider></MemoryRouter>
    </QueryClientProvider>,
  );
}
beforeEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); });

describe("My test page", () => {
  it("explains recording and the no-penalty policy, and needs consent before Start", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: inv() });
    wrap("/my-tests/5", "/my-tests/:id", <MyTestDetailPage />);
    expect(await screen.findByText(/speaking section/i)).toBeInTheDocument();
    expect(screen.getByText(/never fail or reject you automatically/i)).toBeInTheDocument();
    const start = screen.getByRole("button", { name: "Start test" });
    expect(start).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox"));
    expect(start).toBeEnabled();
  });
  it("shows why the test cannot start yet and no start button", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: inv({ can_start: false, start_blocked_reason: "The test opens on 20 Nov 2026." }) });
    wrap("/my-tests/5", "/my-tests/:id", <MyTestDetailPage />);
    expect(await screen.findByText(/test opens on/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start test" })).not.toBeInTheDocument();
  });
  it("lets the applicant accept an invitation", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue({ data: inv({ status: "invited", can_accept: true, can_start: false, start_blocked_reason: "Accept the invitation first." }) });
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: inv() });
    wrap("/my-tests/5", "/my-tests/:id", <MyTestDetailPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Accept invitation" }));
    expect(post).toHaveBeenCalledWith("/test-invitations/5/accept");
    expect(get).toHaveBeenCalled();
  });
  it("offers to accept or decline a suggested alternative time", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: inv({ reschedules: [{ id: 9, reason: "exam", preferred_start: null, status: "alternative_suggested", comment: "How about this?", new_window_start: "2026-11-25T09:00:00Z", new_window_end: "2026-11-25T17:00:00Z", created_at: "2026-11-19T09:00:00Z", decided_at: null }] }) });
    wrap("/my-tests/5", "/my-tests/:id", <MyTestDetailPage />);
    expect(await screen.findByText(/different time was suggested/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept new time" })).toBeInTheDocument();
  });
});

const attempt = (): TakeAttempt => ({
  id: 11, status: "in_progress", assessment_title: "Python Developer assessment", started_at: new Date().toISOString(),
  deadline_at: new Date(Date.now() + 30 * 60 * 1000).toISOString(), server_now: new Date().toISOString(), submitted_at: null, session_id: null, rs_record_seconds: 20,
  sections: [
    { kind: "mcq", title: "MCQ", questions: [{ id: 1, section: "mcq", position: 1, text: "Which keyword defines a function?", options: [{ id: 2, text: "def" }, { id: 0, text: "func" }], marks: 1, selected: null, marked: false, plays_used: 0, plays_allowed: null, recordings_used: 0, recordings_allowed: null }] },
    { kind: "repeat_sentence", title: "Repeat the Sentence", questions: [{ id: 2, section: "repeat_sentence", position: 1, text: null, options: null, marks: 2, selected: null, marked: false, plays_used: 0, plays_allowed: 2, recordings_used: 0, recordings_allowed: 1 }] },
  ],
});

describe("Test runner", () => {
  const open = () => { sessionStorage.setItem("hireai-attempt-session-11", "sess-1"); return wrap("/take/11", "/take/:attemptId", <TestRunnerPage />); };

  it("shows the timer, questions and a no-penalty notice, with no answer key", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: attempt() });
    open();
    expect(await screen.findByText("Which keyword defines a function?")).toBeInTheDocument();
    expect(screen.getByRole("timer")).toHaveTextContent(/^(29|30):\d\d$/);
    expect(screen.getByText(/will not fail your test/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/correct/i);
  });

  it("autosaves a chosen answer with the session header and the original option id", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: attempt() });
    const put = vi.spyOn(api, "put").mockResolvedValue({ data: { saved: 1 } });
    open();
    await userEvent.click(await screen.findByLabelText("def"));
    await waitFor(() => expect(put).toHaveBeenCalled(), { timeout: 4000 });
    const [url, body, cfg] = put.mock.calls[0] as [string, { answers: { question_id: number; selected_index: number }[] }, { headers: Record<string, string> }];
    expect(url).toBe("/attempts/11/answers");
    expect(body.answers[0]).toMatchObject({ question_id: 1, selected_index: 2 });
    expect(cfg.headers["X-Attempt-Session"]).toBe("sess-1");
  });

  it("keeps answers and shows an offline banner when saving fails", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: attempt() });
    vi.spyOn(api, "put").mockRejectedValue(new Error("network"));
    open();
    await userEvent.click(await screen.findByLabelText("def"));
    expect(await screen.findByRole("alert", {}, { timeout: 4000 })).toHaveTextContent(/offline/i);
    expect(screen.getByLabelText("def")).toBeChecked();
  });

  it("asks for confirmation before submitting", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: attempt() });
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} });
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Submit test" }));
    expect(screen.getByText(/cannot change your answers after submitting/i)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Submit now" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/attempts/11/submit", null, expect.anything()));
    expect(await screen.findByText(/has been submitted/i)).toBeInTheDocument();
  });

  it("disables recording until the sentence has been played and never shows the sentence text up front", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: attempt() });
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Question 2: not answered" }));
    expect(screen.getByRole("button", { name: /Record answer/ })).toBeDisabled();
    expect(screen.getByText(/2 play\(s\) left/)).toBeInTheDocument();
    expect(screen.getByText(/accent does not matter/i)).toBeInTheDocument();
  });

  it("tells the applicant when this window no longer owns the session", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: attempt() });
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={["/take/11"]}><ToastProvider><Routes><Route path="/take/:attemptId" element={<TestRunnerPage />} /></Routes></ToastProvider></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByText(/does not hold the session/i)).toBeInTheDocument();
  });
});
