import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Mic, Volume2, WifiOff } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import { Alert, Button, Modal, Spinner } from "@/components/ui";
import { sessionKey } from "./MyTestDetailPage";
import type { TakeAttempt, TakeQuestion } from "@/types";

/**
 * Distraction-free test runner (outside the normal app layout).
 * - The server owns the deadline; the clock here is only a display, corrected by the server's time.
 * - Answers autosave in the background and are retried while offline.
 * - Copy, cut, paste, drag and the right-click menu are blocked while the test is open. This is a deterrent only:
 *   a browser cannot truly stop someone using another device or window.
 * - A browser cannot prevent switching tabs. It can only notice it, so we show a warning when the applicant
 *   comes back and report it. Reports are for reviewers' context ONLY: nothing here ends the test or fails anyone.
 */

type Answer = { selected: number | null; marked: boolean; seq: number };
type ClientEventKind = "tab_hidden" | "tab_visible" | "copy" | "paste" | "offline" | "online" | "mic_denied" | "recording_failed";

function fmt(ms: number) {
  const s = Math.max(0, Math.ceil(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function speak(text: string) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return false;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 0.9;
  window.speechSynthesis.speak(u);
  return true;
}

function SpeakingQuestion({ q, attemptId, headers, seconds, onChange, report, onClosed }: {
  q: TakeQuestion; attemptId: number; headers: Record<string, string>; seconds: number; onChange: (patch: Partial<TakeQuestion>) => void;
  report: (k: ClientEventKind) => void; onClosed: (code?: string) => void;
}) {
  const [msg, setMsg] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [left, setLeft] = useState(seconds);
  const [pending, setPending] = useState<{ blob: Blob; ms: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const rec = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | null>(null);
  const playsLeft = (q.plays_allowed ?? 1) - q.plays_used;
  const takesLeft = (q.recordings_allowed ?? 1) - q.recordings_used;

  const fail = (e: unknown) => {
    const code = (e as { response?: { data?: { error?: { code?: string } } } }).response?.data?.error?.code;
    if (code === "time_up" || code === "attempt_closed" || code === "session_replaced") { onClosed(code); return; }
    setMsg(errorMessage(e));
  };

  const play = async () => {
    setMsg(null);
    try {
      const { data } = await api.post<{ sentence: string; plays_used: number }>(`/attempts/${attemptId}/questions/${q.id}/play`, null, { headers });
      onChange({ plays_used: data.plays_used });
      if (!speak(data.sentence)) setMsg("Your browser cannot speak the sentence aloud. Please try another browser (Chrome, Edge or Safari).");
    } catch (e) { fail(e); }
  };

  const upload = async (blob: Blob, ms: number) => {
    setBusy(true);
    setMsg(null);
    try {
      const fd = new FormData();
      fd.append("file", blob, "answer.webm");
      fd.append("duration_ms", String(ms));
      await api.post(`/attempts/${attemptId}/questions/${q.id}/recording`, fd, { headers });
      setPending(null);
      onChange({ recordings_used: q.recordings_used + 1 });
      setMsg("Recording saved.");
    } catch (e) {
      report("recording_failed");
      setPending({ blob, ms });  // keep it so the applicant can retry without re-recording
      fail(e);
    } finally { setBusy(false); }
  };

  const stop = useCallback(() => {
    if (timer.current) window.clearInterval(timer.current);
    if (rec.current && rec.current.state !== "inactive") rec.current.stop();
  }, []);
  useEffect(() => () => stop(), [stop]);

  const record = async () => {
    setMsg(null);
    if (typeof MediaRecorder === "undefined" || !navigator.mediaDevices?.getUserMedia) { setMsg("This browser cannot record audio. Please use a current version of Chrome, Edge or Safari."); report("recording_failed"); return; }
    let stream: MediaStream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch { report("mic_denied"); setMsg("Microphone access was blocked. Allow the microphone in your browser's address bar, then try again."); return; }
    const chunks: Blob[] = [];
    const r = new MediaRecorder(stream);
    const startedAt = Date.now();
    rec.current = r;
    r.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    r.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      setRecording(false);
      const ms = Date.now() - startedAt;
      void upload(new Blob(chunks, { type: r.mimeType || "audio/webm" }), ms);
    };
    r.start();
    setRecording(true);
    setLeft(seconds);
    timer.current = window.setInterval(() => setLeft((v) => { if (v <= 1) { stop(); return 0; } return v - 1; }), 1000);
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-700">Listen to the sentence, then repeat it aloud exactly as you heard it. Accent does not matter.</p>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" onClick={() => void play()} disabled={playsLeft <= 0 || recording}><Volume2 className="size-4" /> Play sentence</Button>
        <span className="text-sm text-slate-600" aria-live="polite">{playsLeft} play(s) left</span>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {!recording ? (
          <Button onClick={() => void record()} disabled={q.plays_used < 1 || takesLeft <= 0 || busy || !!pending}><Mic className="size-4" /> Record answer</Button>
        ) : (
          <>
            <span className="inline-flex items-center gap-2 rounded-full bg-red-50 px-3 py-1 text-sm font-medium text-red-700" role="status"><span className="size-2 animate-pulse rounded-full bg-red-600" /> Recording… {left}s left</span>
            <Button variant="secondary" onClick={stop}>Stop</Button>
          </>
        )}
        <span className="text-sm text-slate-600">{takesLeft} recording attempt(s) left</span>
      </div>
      {q.plays_used < 1 && <p className="text-xs text-slate-500">Play the sentence first to enable recording.</p>}
      {busy && <p className="text-sm text-slate-600">Saving your recording…</p>}
      {pending && !busy && <Button variant="secondary" onClick={() => void upload(pending.blob, pending.ms)}>Retry upload</Button>}
      {msg && <Alert kind={msg === "Recording saved." ? "success" : "warning"}>{msg}</Alert>}
    </div>
  );
}

export default function TestRunnerPage() {
  const { attemptId } = useParams();
  const navigate = useNavigate();
  const id = Number(attemptId);
  const session = useMemo(() => { try { return sessionStorage.getItem(sessionKey(id)) || ""; } catch { return ""; } }, [id]);
  const headers = useMemo(() => ({ "X-Attempt-Session": session }), [session]);

  const { data, isLoading, error } = useQuery({ queryKey: ["attempt", id], staleTime: Infinity, gcTime: 0, refetchOnWindowFocus: false, queryFn: async () => (await api.get<TakeAttempt>(`/attempts/${id}`)).data });
  const [questions, setQuestions] = useState<TakeQuestion[] | null>(null);
  const [answers, setAnswers] = useState<Record<number, Answer>>({});
  const [index, setIndex] = useState(0);
  const [offset, setOffset] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [offline, setOffline] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [leftCount, setLeftCount] = useState(0);
  const [closed, setClosed] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const dirty = useRef<Set<number>>(new Set());
  const seq = useRef(0);
  const events = useRef<{ kind: ClientEventKind; at: string }[]>([]);
  const submitted = useRef(false);

  useEffect(() => {
    if (!data) return;
    if (data.status === "submitted") { setClosed("submitted"); return; }
    const qs = data.sections.flatMap((s) => s.questions);
    setQuestions(qs);
    setAnswers(Object.fromEntries(qs.filter((q) => q.options).map((q) => [q.id, { selected: q.selected, marked: q.marked, seq: 0 }])));
    setOffset(new Date(data.server_now).getTime() - Date.now());
  }, [data]);

  useEffect(() => { const t = window.setInterval(() => setNow(Date.now()), 500); return () => window.clearInterval(t); }, []);
  const deadline = data ? new Date(data.deadline_at).getTime() : 0;
  const remaining = deadline - (now + offset);

  const handleClosed = useCallback((code?: string) => { setClosed(code ?? "submitted"); }, []);

  const flush = useCallback(async () => {
    if (dirty.current.size === 0 || closed) return true;
    const ids = [...dirty.current];
    const body = { answers: ids.map((qid) => ({ question_id: qid, selected_index: answers[qid]?.selected ?? null, marked_for_review: answers[qid]?.marked ?? false, seq: answers[qid]?.seq ?? 0 })) };
    try {
      await api.put(`/attempts/${id}/answers`, body, { headers });
      ids.forEach((qid) => { if ((answers[qid]?.seq ?? 0) === body.answers.find((a) => a.question_id === qid)?.seq) dirty.current.delete(qid); });
      setOffline(false);
      return true;
    } catch (e) {
      const code = (e as { response?: { data?: { error?: { code?: string } } } }).response?.data?.error?.code;
      if (code === "time_up" || code === "attempt_closed" || code === "session_replaced") { handleClosed(code); return true; }
      setOffline(true);
      return false;
    }
  }, [answers, closed, headers, id, handleClosed]);

  // debounce + retry loop
  useEffect(() => { const t = window.setInterval(() => { void flush(); }, 1500); return () => window.clearInterval(t); }, [flush]);

  const sendEvents = useCallback(async () => {
    if (events.current.length === 0 || closed) return;
    const batch = events.current.splice(0, 50);
    try { await api.post(`/attempts/${id}/events`, { events: batch }, { headers }); } catch { /* informational only; never block the test */ }
  }, [closed, headers, id]);
  const report = useCallback((kind: ClientEventKind) => { events.current.push({ kind, at: new Date().toISOString() }); }, []);
  useEffect(() => {
    const vis = () => {
      report(document.hidden ? "tab_hidden" : "tab_visible");
      if (document.hidden) setLeftCount((n) => n + 1);
      else setNotice("You left the test window. This was recorded for the reviewers and the timer kept running. Please stay on this page until you submit.");
    };
    const on = () => { setOffline(false); report("online"); };
    const off = () => { setOffline(true); report("offline"); };
    // Blocked, but still reported (informational). "cut" is reported as "copy"; the server only knows these kinds.
    const block = (kind: ClientEventKind | null) => (e: Event) => { e.preventDefault(); if (kind) report(kind); setNotice("Copy and paste are turned off during this test."); };
    const copy = block("copy"), cut = block("copy"), paste = block("paste"), menu = block(null), drag = block(null);
    document.addEventListener("visibilitychange", vis);
    window.addEventListener("online", on); window.addEventListener("offline", off);
    document.addEventListener("copy", copy); document.addEventListener("cut", cut); document.addEventListener("paste", paste);
    document.addEventListener("contextmenu", menu); document.addEventListener("dragstart", drag);
    const t = window.setInterval(() => { void sendEvents(); }, 10000);
    return () => { document.removeEventListener("visibilitychange", vis); window.removeEventListener("online", on); window.removeEventListener("offline", off); document.removeEventListener("copy", copy); document.removeEventListener("cut", cut); document.removeEventListener("paste", paste); document.removeEventListener("contextmenu", menu); document.removeEventListener("dragstart", drag); window.clearInterval(t); };
  }, [report, sendEvents]);

  const submit = useCallback(async () => {
    if (submitted.current) return;
    submitted.current = true;
    setSubmitting(true);
    await flush();
    await sendEvents();
    try { await api.post(`/attempts/${id}/submit`, null, { headers }); setClosed("submitted"); }
    catch (e) {
      const code = (e as { response?: { data?: { error?: { code?: string } } } }).response?.data?.error?.code;
      if (code === "session_replaced") setClosed(code); else { submitted.current = false; setOffline(true); }
    } finally { setSubmitting(false); setConfirm(false); }
  }, [flush, sendEvents, headers, id]);

  useEffect(() => { if (data && questions && !closed && remaining <= 0) void submit(); }, [remaining, data, questions, closed, submit]);

  const select = (q: TakeQuestion, optionId: number | null, marked?: boolean) => {
    seq.current += 1;
    setAnswers((a) => ({ ...a, [q.id]: { selected: optionId === undefined ? a[q.id]?.selected ?? null : optionId, marked: marked ?? a[q.id]?.marked ?? false, seq: seq.current } }));
    dirty.current.add(q.id);
  };
  const patchQuestion = (qid: number, patch: Partial<TakeQuestion>) => setQuestions((qs) => qs && qs.map((q) => (q.id === qid ? { ...q, ...patch } : q)));

  if (isLoading) return <Spinner label="Loading your test…" />;
  if (error) return <div className="mx-auto max-w-md p-6"><Alert kind="error">{errorMessage(error)}</Alert><Link to="/my-tests" className="mt-3 inline-block text-sm text-brand-700 underline">Back to My tests</Link></div>;

  if (closed) {
    const text: Record<string, string> = {
      submitted: "Your test has been submitted. Thank you. The recruitment team will review your responses and contact you about next steps.",
      time_up: "Time is up. Your answers were submitted automatically.",
      attempt_closed: "This test has already been submitted.",
      session_replaced: "This test was opened in another window or device, so this window is no longer active. Go back to My tests and choose Resume to continue here.",
    };
    return <div className="mx-auto max-w-lg p-6"><Alert kind={closed === "session_replaced" ? "warning" : "success"}>{text[closed] ?? text.submitted}</Alert><Button className="mt-4" onClick={() => navigate("/my-tests")}>Back to My tests</Button></div>;
  }
  if (!data || !questions) return <Spinner />;
  if (!session) return <div className="mx-auto max-w-lg p-6"><Alert kind="warning">This window does not hold the session for your test. Open it again from My tests and choose Resume.</Alert><Button className="mt-4" onClick={() => navigate("/my-tests")}>Go to My tests</Button></div>;

  const q = questions[index];
  const a = answers[q.id];
  const sectionTitle = data.sections.find((s) => s.kind === q.section)?.title ?? "";
  const answered = questions.filter((x) => (x.options ? answers[x.id]?.selected != null : x.recordings_used > 0)).length;
  const low = remaining < 5 * 60 * 1000;

  return (
    <div className="min-h-screen select-none bg-slate-50">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white px-4 py-3">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3">
          <div><h1 className="text-base font-semibold text-slate-900">{data.assessment_title}</h1><p className="text-xs text-slate-500">{answered} of {questions.length} answered</p></div>
          <div className="flex items-center gap-3">
            <span role="timer" aria-label="Time remaining" className={`rounded-md px-3 py-1 font-mono text-lg tabular-nums ${low ? "bg-red-50 text-red-700" : "bg-slate-100 text-slate-800"}`}>{fmt(remaining)}</span>
            <Button onClick={() => setConfirm(true)} loading={submitting}>Submit test</Button>
          </div>
        </div>
      </header>
      {notice && <div className="flex items-center justify-center gap-3 bg-amber-100 px-4 py-2 text-center text-sm text-amber-900" role="alert">{notice}{leftCount > 0 && <span className="text-xs">({leftCount} time{leftCount === 1 ? "" : "s"} away so far)</span>}<button type="button" onClick={() => setNotice(null)} className="rounded px-2 text-xs font-medium underline">Dismiss</button></div>}
      {offline && <div className="bg-amber-100 px-4 py-2 text-center text-sm text-amber-900" role="alert"><WifiOff className="mr-1 inline size-4" /> You appear to be offline. Your answers are kept here and will be saved when the connection returns. Keep this page open.</div>}
      <div className="mx-auto grid max-w-5xl gap-6 p-4 lg:grid-cols-[1fr_16rem]">
        <main className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{sectionTitle} · question {q.position} · {q.marks} mark{q.marks === 1 ? "" : "s"}</p>
          {q.options ? (
            <>
              <h2 className="mt-2 whitespace-pre-wrap text-lg text-slate-900">{q.text}</h2>
              <div role="radiogroup" aria-label="Answer options" className="mt-4 space-y-2">
                {q.options.map((o) => (
                  <label key={o.id} className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm ${a?.selected === o.id ? "border-brand-600 bg-brand-50" : "border-slate-200 hover:bg-slate-50"}`}>
                    <input type="radio" name={`q-${q.id}`} className="mt-0.5" checked={a?.selected === o.id} onChange={() => select(q, o.id)} />
                    <span>{o.text}</span>
                  </label>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button variant="ghost" size="sm" onClick={() => select(q, a?.selected ?? null, !(a?.marked))}>{a?.marked ? "Unmark for review" : "Mark for review"}</Button>
                {a?.selected != null && <Button variant="ghost" size="sm" onClick={() => select(q, null)}>Clear answer</Button>}
              </div>
            </>
          ) : (
            <div className="mt-3"><SpeakingQuestion key={q.id} q={q} attemptId={id} headers={headers} seconds={data.rs_record_seconds ?? 20} onChange={(p) => patchQuestion(q.id, p)} report={report} onClosed={handleClosed} /></div>
          )}
          <div className="mt-6 flex justify-between border-t border-slate-100 pt-4">
            <Button variant="secondary" disabled={index === 0} onClick={() => setIndex(index - 1)}>Previous</Button>
            <Button variant="secondary" disabled={index === questions.length - 1} onClick={() => setIndex(index + 1)}>Next</Button>
          </div>
        </main>
        <aside className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" aria-label="Question navigator">
          <h2 className="mb-2 text-sm font-semibold text-slate-900">Questions</h2>
          <div className="grid grid-cols-6 gap-1.5">
            {questions.map((x, i) => {
              const done = x.options ? answers[x.id]?.selected != null : x.recordings_used > 0;
              const mk = answers[x.id]?.marked;
              return (
                <button key={x.id} type="button" onClick={() => setIndex(i)} aria-label={`Question ${i + 1}: ${done ? "answered" : "not answered"}${mk ? ", marked for review" : ""}`} aria-current={i === index}
                  className={`h-8 rounded text-xs font-medium ring-1 ring-inset ${i === index ? "ring-2 ring-brand-600" : "ring-slate-300"} ${done ? "bg-emerald-100 text-emerald-800" : "bg-white text-slate-700"} ${mk ? "underline decoration-amber-500 decoration-2" : ""}`}>{i + 1}</button>
              );
            })}
          </div>
          <p className="mt-3 text-xs text-slate-500">Green = answered. Underlined = marked for review.</p>
          <p className="mt-3 text-xs text-slate-500">Copy and paste are turned off. Leaving this tab is recorded for the reviewers; it cannot be blocked, and it does not fail your test automatically.</p>
        </aside>
      </div>
      <Modal open={confirm} onClose={() => setConfirm(false)} title="Submit your test?"
        footer={<><Button variant="secondary" onClick={() => setConfirm(false)}>Keep working</Button><Button loading={submitting} onClick={() => void submit()}>Submit now</Button></>}>
        <p className="text-sm text-slate-700">You answered {answered} of {questions.length} questions{questions.some((x) => answers[x.id]?.marked) ? " and some are marked for review" : ""}. You cannot change your answers after submitting.</p>
      </Modal>
    </div>
  );
}
