import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Alert, Badge, Button, Card, ErrorState, Field, Modal, PageHeader, Spinner, Textarea, TextInput } from "@/components/ui";
import { ApplicationStatusBadge } from "@/components/badges";
import InterviewDialog from "@/components/InterviewDialog";
import { useToast } from "@/components/Toast";
import { formatDateTime, humanize } from "@/utils/format";
import type { EvalDetail, EvalItem } from "@/types";

const pct = (v: number | null) => (v == null ? "n/a" : `${Math.round(v * 100)}%`);

function OverrideDialog({ evalId, item, onClose }: { evalId: number; item: EvalItem; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [marks, setMarks] = useState(String(item.final_marks ?? item.auto_marks ?? 0));
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => api.post(`/evaluations/${evalId}/items/${item.id}/override`, { marks: Number(marks), reason }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["evaluation", evalId] }); void qc.invalidateQueries({ queryKey: ["evaluations"] }); toast.success("Score updated and recorded."); onClose(); },
    onError: (e) => setErr(errorMessage(e)),
  });
  return (
    <Modal open onClose={onClose} title={`Set score for question ${item.position}`}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={m.isPending} disabled={reason.trim().length < 5 || marks === "" || Number.isNaN(Number(marks))} onClick={() => { setErr(null); m.mutate(); }}>Save score</Button></>}>
      <div className="space-y-4">
        {err && <Alert kind="error">{err}</Alert>}
        <p className="text-sm text-slate-600">Every change is recorded with your name, the time, the original and revised score, and your reason.</p>
        <Field label={`Marks (0 to ${item.max_marks})`} htmlFor="ov-marks"><TextInput id="ov-marks" type="number" step="0.25" min={0} max={item.max_marks} value={marks} onChange={(e) => setMarks(e.target.value)} /></Field>
        <Field label="Reason (required)" htmlFor="ov-reason"><Textarea id="ov-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </div>
    </Modal>
  );
}

function ItemCard({ item, canEdit, evalId, onOverride }: { item: EvalItem; canEdit: boolean; evalId: number; onOverride: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useMutation({
    mutationFn: () => api.post(`/evaluations/${evalId}/items/${item.id}/confirm`, {}),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["evaluation", evalId] }); toast.success("Provisional score confirmed."); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const sp = item.speech;
  const marks = item.final_marks == null ? <Badge tone="amber">Not scored</Badge> : <span className="tabular-nums">{item.final_marks} / {item.max_marks}</span>;
  return (
    <li className="rounded-lg border border-slate-200 p-3 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="font-medium text-slate-900">{item.position}. {item.text}</p>
        <div className="flex items-center gap-2">{item.overridden && <Badge tone="purple">Manually scored</Badge>}{marks}</div>
      </div>
      {item.options ? (
        <div className="mt-2 space-y-1">
          <p className={item.unanswered ? "text-slate-500" : item.is_correct ? "text-emerald-700" : "text-red-700"}>{item.unanswered ? "Not answered" : `Answered: ${item.selected_text}`} {!item.unanswered && (item.is_correct ? "✓ correct" : "✗ incorrect")}</p>
          {!item.is_correct && <p className="text-slate-600">Correct answer: {item.correct_text}</p>}
        </div>
      ) : (
        <div className="mt-2 space-y-2">
          {item.needs_review && item.review_note && <Alert kind="warning">{item.review_note}</Alert>}
          {!item.needs_review && item.review_note && <p className="text-xs text-slate-500">{item.review_note}</p>}
          {sp && (
            <div className="rounded-md bg-slate-50 p-2">
              <p><span className="text-slate-500">Expected:</span> {sp.expected}</p>
              <p><span className="text-slate-500">Recognised:</span> {sp.recognized || <em className="text-slate-400">nothing</em>}</p>
              <div className="mt-1 flex flex-wrap gap-1 text-xs">
                <Badge>Accuracy {pct(sp.accuracy)}</Badge><Badge>Complete {pct(sp.completeness)}</Badge><Badge tone={sp.confidence != null && sp.confidence >= 0.6 ? "green" : "amber"}>Confidence {sp.confidence == null ? "unknown" : pct(sp.confidence)}</Badge>
                {sp.order_differs && <Badge tone="amber">Word order differs</Badge>}{sp.is_mock && <Badge tone="amber">MOCK speech-to-text</Badge>}
              </div>
              {sp.missing.length > 0 && <p className="mt-1 text-xs text-slate-600">Missing: {sp.missing.join(", ")}</p>}
              {sp.substituted.length > 0 && <p className="text-xs text-slate-600">Different: {sp.substituted.map((x) => `${x.expected} → ${x.heard}`).join(", ")}</p>}
              {sp.near_matches.length > 0 && <p className="text-xs text-slate-600">Possible recognition slips (half credit): {sp.near_matches.map((x) => `${x.expected} / ${x.heard}`).join(", ")}</p>}
              {sp.error && <p className="text-xs text-red-700">Speech service: {sp.error}</p>}
            </div>
          )}
          {item.recordings.map((r) => (
            <div key={r.id} className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
              <span>Take {r.attempt_no}{r.is_final ? " (scored)" : ""}</span>
              <audio controls preload="none" src={`/api/recordings/${r.id}/file`} aria-label={`Recording for question ${item.position}, take ${r.attempt_no}`} />
            </div>
          ))}
          {item.recordings.length > 0 && <p className="text-xs text-slate-500">Judge the content repeated, never the accent. Each playback is logged.</p>}
        </div>
      )}
      {canEdit && (
        <div className="mt-2 flex flex-wrap gap-2">
          {item.final_marks == null && item.auto_marks != null && <Button size="sm" variant="secondary" loading={confirm.isPending} onClick={() => confirm.mutate()}>Confirm suggested {item.auto_marks}</Button>}
          <Button size="sm" variant="ghost" onClick={onOverride}>{item.final_marks == null ? "Enter score" : "Change score"}</Button>
        </div>
      )}
    </li>
  );
}

export default function ResultDetailPage() {
  const { id } = useParams();
  const evalId = Number(id);
  const qc = useQueryClient();
  const toast = useToast();
  const [override, setOverride] = useState<EvalItem | null>(null);
  const [comment, setComment] = useState("");
  const [dlg, setDlg] = useState<null | "release" | "reopen" | "withdraw" | "reject" | "shortlist" | "select">(null);
  const [text, setText] = useState("");
  const [interview, setInterview] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const { data: e, isLoading, error, refetch } = useQuery({ queryKey: ["evaluation", evalId], queryFn: async () => (await api.get<EvalDetail>(`/evaluations/${evalId}`)).data });
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["evaluation", evalId] }); void qc.invalidateQueries({ queryKey: ["evaluations"] }); };
  const act = useMutation({
    mutationFn: async (v: { path: string; body?: unknown; ok: string }) => { await api.post(v.path, v.body ?? {}); return v.ok; },
    onSuccess: (ok) => { refresh(); setDlg(null); setText(""); setErr(null); toast.success(ok); },
    onError: (er) => setErr(errorMessage(er)),
  });
  const addComment = useMutation({ mutationFn: () => api.post(`/evaluations/${evalId}/comments`, { body: comment }), onSuccess: () => { setComment(""); refresh(); }, onError: (er) => toast.error(errorMessage(er)) });

  if (isLoading) return <Spinner />;
  if (error || !e) return <Card><ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /></Card>;
  const final = e.status === "final";
  const decide = (decision: string, ok: string) => act.mutate({ path: `/applications/${e.application_id}/decision`, body: { decision, reason: text || null }, ok });
  const dialogs: Record<string, { title: string; help: string; label: string; required: boolean; confirm: string; run: () => void; danger?: boolean }> = {
    release: { title: "Release result to the applicant", help: "The applicant will see their scores and this feedback, nothing else: no answer keys, no internal comments.", label: "Feedback for the applicant (optional)", required: false, confirm: "Release result", run: () => act.mutate({ path: `/evaluations/${evalId}/release`, body: { feedback: text || null }, ok: "Result released." }) },
    reopen: { title: "Reopen for changes", help: "The evaluation returns to review so scores can be changed.", label: "Reason", required: true, confirm: "Reopen", run: () => act.mutate({ path: `/evaluations/${evalId}/reopen`, body: { reason: text }, ok: "Evaluation reopened." }) },
    withdraw: { title: "Withdraw release", help: "The applicant will no longer see this result.", label: "Reason", required: true, confirm: "Withdraw", run: () => act.mutate({ path: `/evaluations/${evalId}/withdraw-release`, body: { reason: text }, ok: "Release withdrawn." }) },
    shortlist: { title: "Shortlist candidate", help: "The applicant is notified. A person makes this decision; the score is only an input.", label: "Message to the applicant (optional)", required: false, confirm: "Shortlist", run: () => decide("shortlist", "Candidate shortlisted.") },
    select: { title: "Select candidate", help: "The applicant is notified of the selection.", label: "Message to the applicant (optional)", required: false, confirm: "Select", run: () => decide("select", "Candidate selected.") },
    reject: { title: "Reject candidate", help: "The applicant is notified and sees your reason. Give a fair, job-related reason.", label: "Reason (required)", required: true, confirm: "Reject", danger: true, run: () => decide("reject", "Candidate rejected.") },
  };
  const d = dlg ? dialogs[dlg] : null;

  return (
    <>
      <PageHeader title={e.candidate_name} description={`${e.opening_title} · ${e.assessment_title}`} actions={<Link to="/results" className="text-sm text-brand-700 hover:underline">← All results</Link>} />
      <div className="mb-4 space-y-2">
        {e.speech_is_mock && <Alert kind="warning"><strong>MOCK speech-to-text.</strong> It cannot understand audio, so every recording below needs a person to listen and score it. Configure a real speech provider for automatic suggestions.</Alert>}
        {e.assessment_is_mock && <Alert kind="warning"><strong>MOCK assessment content.</strong> These questions were generated in mock mode.</Alert>}
      </div>

      <Card className="mb-6 p-5">
        <div className="flex flex-wrap items-center gap-2"><Badge tone={final ? "green" : "blue"}>{final ? "Approved" : "In review"}</Badge>{e.released_at && <Badge tone="purple">Released {formatDateTime(e.released_at)}</Badge>}<ApplicationStatusBadge status={e.application_status} /></div>
        <p className="mt-4 text-3xl font-semibold tabular-nums text-slate-900">{e.total_obtained}<span className="text-lg font-normal text-slate-500"> / {e.total_marks}</span>{e.percentage != null && <span className="ml-3 text-lg text-slate-600">{e.percentage}%</span>}</p>
        <table className="mt-3 w-full max-w-lg text-sm"><tbody>
          {e.sections.map((s) => (
            <tr key={s.kind} className="border-b border-slate-100"><td className="py-1.5">{s.title}</td><td className="py-1.5 tabular-nums">{s.obtained} / {s.total}</td>
              <td className="py-1.5 text-xs text-slate-500">{s.kind === "repeat_sentence" ? (s.unresolved ? `${s.unresolved} to score` : "") : `${s.correct} correct · ${s.incorrect} wrong · ${s.unanswered} blank`}</td></tr>
          ))}
        </tbody></table>
        <p className="mt-3 text-xs text-slate-500">Test taken {formatDateTime(e.test_date)} · time used {e.time_taken_seconds != null ? `${Math.floor(e.time_taken_seconds / 60)} of ${e.duration_minutes} min` : "n/a"} · {e.candidate_email}</p>
        {e.summary && <p className="mt-3 rounded-md bg-slate-50 p-3 text-sm text-slate-700">{e.summary}</p>}
        {e.blockers.map((b) => <div key={b} className="mt-3"><Alert kind="warning">{b}</Alert></div>)}
        {e.applicant_feedback && <p className="mt-3 text-sm text-slate-600"><strong>Feedback shown to applicant:</strong> {e.applicant_feedback}</p>}
        <div className="mt-4 flex flex-wrap gap-2">
          {!final && <Button loading={act.isPending && act.variables?.path.endsWith("finalize")} disabled={e.blockers.length > 0} onClick={() => act.mutate({ path: `/evaluations/${evalId}/finalize`, ok: "Evaluation approved." })}>Approve evaluation</Button>}
          {!final && <Button variant="secondary" onClick={() => act.mutate({ path: `/evaluations/${evalId}/rerun-speech`, ok: "Speech processing re-run." })}>Re-run speech processing</Button>}
          {final && !e.released_at && <Button onClick={() => { setErr(null); setDlg("release"); }}>Release to applicant</Button>}
          {final && !e.released_at && <Button variant="secondary" onClick={() => { setErr(null); setDlg("reopen"); }}>Reopen</Button>}
          {e.released_at && <Button variant="secondary" onClick={() => { setErr(null); setDlg("withdraw"); }}>Withdraw release</Button>}
        </div>
        {err && !dlg && <div className="mt-3"><Alert kind="error">{err}</Alert></div>}
      </Card>

      {final && (
        <Card className="mb-6 p-5">
          <h2 className="text-sm font-semibold text-slate-900">Decision</h2>
          <p className="mb-3 text-xs text-slate-500">Decisions are made by people. A score never shortlists or rejects anyone by itself.</p>
          <div className="flex flex-wrap gap-2">
            {e.application_status === "approved" && <Button onClick={() => { setErr(null); setDlg("shortlist"); }}>Shortlist</Button>}
            {e.application_status === "shortlisted" && <><Button onClick={() => setInterview(true)}>Schedule interview</Button><Button variant="secondary" onClick={() => { setErr(null); setDlg("select"); }}>Select</Button></>}
            {(e.application_status === "approved" || e.application_status === "shortlisted") && <Button variant="ghost" onClick={() => { setErr(null); setDlg("reject"); }}>Reject</Button>}
            {["selected", "rejected"].includes(e.application_status) && <span className="text-sm text-slate-600">Decision recorded: <ApplicationStatusBadge status={e.application_status} /></span>}
          </div>
        </Card>
      )}

      {e.groups.map((g) => (
        <Card key={g.kind} className="mb-6 p-5">
          <h2 className="mb-3 text-sm font-semibold text-slate-900">{g.title}</h2>
          <ul className="space-y-3">{g.items.map((it) => <ItemCard key={it.id} item={it} canEdit={e.can_edit} evalId={evalId} onOverride={() => setOverride(it)} />)}</ul>
        </Card>
      ))}

      {e.overrides.length > 0 && (
        <Card className="mb-6 p-5">
          <h2 className="mb-3 text-sm font-semibold text-slate-900">Manual score changes</h2>
          <ul className="space-y-2 text-sm">{e.overrides.map((o) => <li key={o.id} className="border-b border-slate-100 pb-2"><span className="font-medium">{humanize(o.section)} Q{o.question_position}: {o.original_marks ?? "unscored"} → {o.revised_marks}</span> <span className="text-slate-500">by {o.changed_by ?? "unknown"} · {formatDateTime(o.changed_at)}</span><span className="block text-slate-600">“{o.reason}”</span></li>)}</ul>
        </Card>
      )}

      <Card className="p-5">
        <h2 className="mb-1 text-sm font-semibold text-slate-900">Reviewer comments</h2>
        <p className="mb-3 text-xs text-slate-500">Internal. Never shown to the applicant.</p>
        <div className="flex gap-2"><TextInput aria-label="Add a comment" placeholder="Add a comment" value={comment} onChange={(ev) => setComment(ev.target.value)} /><Button loading={addComment.isPending} disabled={!comment.trim()} onClick={() => addComment.mutate()}>Add</Button></div>
        <ul className="mt-3 space-y-2 text-sm">{e.comments.map((c) => <li key={c.id} className="border-b border-slate-100 pb-2">{c.body}<span className="block text-xs text-slate-500">{c.author ?? "unknown"} · {formatDateTime(c.created_at)}</span></li>)}</ul>
      </Card>

      {override && <OverrideDialog evalId={evalId} item={override} onClose={() => setOverride(null)} />}
      {interview && <InterviewDialog applicationId={e.application_id} onClose={() => setInterview(false)} />}
      {d && (
        <Modal open onClose={() => setDlg(null)} title={d.title}
          footer={<><Button variant="secondary" onClick={() => setDlg(null)}>Cancel</Button><Button variant={d.danger ? "danger" : "primary"} loading={act.isPending} disabled={d.required && text.trim().length < 5} onClick={() => { setErr(null); d.run(); }}>{d.confirm}</Button></>}>
          <div className="space-y-3">{err && <Alert kind="error">{err}</Alert>}<p className="text-sm text-slate-600">{d.help}</p><Field label={d.label} htmlFor="dlg-text"><Textarea id="dlg-text" rows={3} value={text} onChange={(ev) => setText(ev.target.value)} /></Field></div>
        </Modal>
      )}
    </>
  );
}
