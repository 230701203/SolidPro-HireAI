import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Pencil, Plus, RefreshCw, Trash2, Volume2, X } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import { Alert, Badge, Button, Card, ConfirmDialog, ErrorState, Field, Modal, PageHeader, Spinner, Textarea, TextInput } from "@/components/ui";
import QuestionEditor, { draftFrom, emptyDraft, toBody, type QuestionDraft } from "@/components/QuestionEditor";
import { AssessmentStatusBadge } from "./AssessmentsPage";
import { useToast } from "@/components/Toast";
import ScheduleDialog from "@/components/ScheduleDialog";
import { ScheduleStatusBadge } from "@/components/ScheduleBadge";
import { useAuth } from "@/contexts/AuthContext";
import { formatDateTime } from "@/utils/format";
import type { ScheduleListItem, AQuestion, AssessmentDetail, ASection, Bank, BankQuestion, Page, SectionKind, VersionDetail } from "@/types";

const SOURCE_LABEL = { ai: "AI", template: "Mock content", bank: "Question bank", manual: "Written by hand" } as const;
const STATUS_TONE = { pending: "amber", approved: "green", rejected: "red" } as const;

function speak(text: string) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 0.9;
  window.speechSynthesis.speak(u);
}

function QuestionCard({ q, d, busy, onApprove, onReject, onEdit, onRegenerate, onDelete }: {
  q: AQuestion; d: AssessmentDetail; busy: boolean; onApprove: () => void; onReject: () => void; onEdit: () => void; onRegenerate: () => void; onDelete: () => void;
}) {
  const rs = q.section === "repeat_sentence";
  const canSpeak = typeof window !== "undefined" && "speechSynthesis" in window;
  return (
    <li className={`rounded-lg border p-4 ${q.status === "rejected" ? "border-slate-200 bg-slate-50 opacity-75" : "border-slate-200 bg-white"}`}>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
        <span className="font-medium text-slate-500">#{q.position}</span>
        <Badge tone={STATUS_TONE[q.status]}>{q.status === "pending" ? "Needs review" : q.status === "approved" ? "Approved" : "Rejected"}</Badge>
        <Badge>{SOURCE_LABEL[q.source]}</Badge><Badge>{q.difficulty}</Badge>
        {q.topic && !rs && <Badge>{q.topic}</Badge>}{q.skill && <Badge tone="blue">{q.skill}</Badge>}
        <span className="text-slate-500">{q.marks} mark{q.marks === 1 ? "" : "s"}</span>
        {q.edited && <span className="text-slate-500">edited</span>}
      </div>
      {q.is_placeholder && <div className="mb-2"><Alert kind="warning">Placeholder. Rewrite this question (Edit) or delete it. It cannot be approved as it is.</Alert></div>}
      <p className="text-sm text-slate-900">{rs ? <><span className="text-xs uppercase tracking-wide text-slate-500">Expected sentence: </span>{q.text}</> : q.text}</p>
      {rs && (
        <div className="mt-2 flex items-center gap-3 text-xs text-slate-500">
          {canSpeak && <Button size="sm" variant="secondary" onClick={() => speak(q.text)}><Volume2 className="size-4" /> Preview audio</Button>}
          <span>Recording limit {String(d.config.rs_record_seconds)}s · replays {String(d.config.rs_max_replays)} · attempts {String(d.config.rs_max_attempts)}</span>
        </div>
      )}
      {q.options && (
        <ol className="mt-2 space-y-1 text-sm">
          {q.options.map((o, i) => (
            <li key={i} className={`flex items-start gap-2 rounded px-2 py-1 ${i === q.correct_index ? "bg-green-50 text-green-900" : "text-slate-700"}`}>
              <span className="font-medium">{String.fromCharCode(65 + i)}.</span><span>{o}</span>{i === q.correct_index && <span className="ml-auto text-xs font-medium">Correct answer</span>}
            </li>
          ))}
        </ol>
      )}
      {q.explanation && <p className="mt-2 text-xs text-slate-600"><span className="font-medium">Explanation:</span> {q.explanation}</p>}
      {q.status === "rejected" && q.reject_reason && <p className="mt-2 text-xs text-slate-600">Rejected: {q.reject_reason}</p>}
      {q.reviewed_by_name && q.status !== "pending" && <p className="mt-1 text-xs text-slate-500">Reviewed by {q.reviewed_by_name}</p>}
      {d.can_edit && (
        <div className="mt-3 flex flex-wrap gap-2">
          {q.status !== "approved" && !q.is_placeholder && <Button size="sm" disabled={busy} onClick={onApprove}><Check className="size-4" /> Approve</Button>}
          {q.status !== "rejected" && <Button size="sm" variant="secondary" disabled={busy} onClick={onReject}><X className="size-4" /> Reject</Button>}
          <Button size="sm" variant="secondary" disabled={busy} onClick={onEdit}><Pencil className="size-4" /> Edit</Button>
          {d.can_generate && <Button size="sm" variant="ghost" disabled={busy} onClick={onRegenerate}><RefreshCw className="size-4" /> Regenerate</Button>}
          <Button size="sm" variant="ghost" disabled={busy} onClick={onDelete}><Trash2 className="size-4" /> Delete</Button>
        </div>
      )}
    </li>
  );
}

function BankPicker({ onPick, onClose }: { onPick: (id: number) => void; onClose: () => void }) {
  const [search, setSearch] = useState("");
  const banks = useQuery({ queryKey: ["banks"], queryFn: async () => (await api.get<Bank[]>("/question-banks")).data });
  const bankId = banks.data?.find((b) => b.is_active)?.id;
  const qs = useQuery({
    queryKey: ["bank-questions-picker", bankId, search], enabled: !!bankId,
    queryFn: async () => (await api.get<Page<BankQuestion>>(`/question-banks/${bankId}/questions`, { params: { active: true, search: search || undefined, page_size: 30 } })).data,
  });
  return (
    <Modal open wide onClose={onClose} title="Add an aptitude question from the bank" footer={<Button variant="secondary" onClick={onClose}>Close</Button>}>
      <TextInput aria-label="Search bank" placeholder="Search questions" value={search} onChange={(e) => setSearch(e.target.value)} className="mb-3" />
      {qs.isLoading ? <Spinner /> : (
        <ul className="max-h-96 space-y-2 overflow-y-auto">
          {qs.data?.items.map((q) => (
            <li key={q.id} className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 p-3 text-sm">
              <span><span className="mb-1 flex gap-1.5"><Badge>{q.topic}</Badge><Badge>{q.difficulty}</Badge></span>{q.text}</span>
              <Button size="sm" onClick={() => onPick(q.id)}>Add</Button>
            </li>
          ))}
          {qs.data?.items.length === 0 && <li className="text-sm text-slate-500">No matching questions.</li>}
        </ul>
      )}
    </Modal>
  );
}

function VersionDialog({ id, version, onClose }: { id: number; version: number; onClose: () => void }) {
  const { data, isLoading } = useQuery({ queryKey: ["assessment-version", id, version], queryFn: async () => (await api.get<VersionDetail>(`/assessments/${id}/versions/${version}`)).data });
  return (
    <Modal open onClose={onClose} title={`Approved version ${version}`} footer={<Button variant="secondary" onClick={onClose}>Close</Button>}>
      {isLoading || !data ? <Spinner /> : (
        <div className="space-y-3 text-sm">
          {data.integrity_ok ? <Alert kind="success">Integrity check passed: the stored content still matches its fingerprint.</Alert> : <Alert kind="error">Integrity check FAILED. This version must not be used.</Alert>}
          <p className="text-slate-600">Approved by {data.approved_by_name ?? "unknown"} on {formatDateTime(data.approved_at)}. {data.total_marks} marks, {data.duration_minutes} minutes.</p>
          <ul className="space-y-1">{data.snapshot.sections.map((s) => <li key={s.kind}>{s.title}: {s.questions.length} questions, {s.total_marks} marks</li>)}</ul>
          <p className="break-all font-mono text-xs text-slate-500">SHA-256 {data.content_hash}</p>
          <p className="text-xs text-slate-500">This version is frozen. Editing the assessment or the question bank never changes it.</p>
        </div>
      )}
    </Modal>
  );
}

type Dialog =
  | { kind: "edit"; q: AQuestion } | { kind: "add"; section: SectionKind } | { kind: "bank" } | { kind: "reject"; q: AQuestion }
  | { kind: "delete"; q: AQuestion } | { kind: "approve" } | { kind: "version"; v: number } | { kind: "deleteAll" } | null;

export default function AssessmentDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [dialog, setDialog] = useState<Dialog>(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const key = ["assessment", id];
  const { hasPermission } = useAuth();
  const [scheduling, setScheduling] = useState(false);
  const { data: d, isLoading, error, refetch } = useQuery({ queryKey: key, queryFn: async () => (await api.get<AssessmentDetail>(`/assessments/${id}`)).data });

  const canSchedule = hasPermission("schedule_tests");
  const { data: sched } = useQuery({
    queryKey: ["schedules", "for-application", d?.application_id], enabled: canSchedule && !!d?.published_version,
    queryFn: async () => (await api.get<{ items: ScheduleListItem[] }>("/schedules", { params: { application_id: d!.application_id, page_size: 20 } })).data.items,
  });
  const activeSchedule = sched?.find((x) => ["invited", "accepted", "in_progress"].includes(x.status));

  const done = (next: AssessmentDetail, message?: string) => {
    qc.setQueryData(key, next);
    void qc.invalidateQueries({ queryKey: ["assessments"] });
    setDialog(null); setText(""); setErr(null);
    if (message) toast.success(message);
  };
  const act = useMutation({
    mutationFn: async (p: { method: "post" | "patch" | "delete"; url: string; body?: unknown; ok?: string }) => ({ r: (await api[p.method]<AssessmentDetail>(`/assessments/${id}${p.url}`, p.body as never)).data, ok: p.ok }),
    onSuccess: ({ r, ok }) => done(r, ok),
    onError: (e) => { setErr(errorMessage(e)); if (!dialog) toast.error(errorMessage(e)); },
  });
  const remove = useMutation({
    mutationFn: () => api.delete(`/assessments/${id}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["assessments"] }); toast.success("Assessment deleted."); navigate("/assessments"); },
    onError: (e) => { setDialog(null); toast.error(errorMessage(e)); },
  });

  if (isLoading) return <Spinner />;
  if (error || !d) return <Card><ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /></Card>;
  const busy = act.isPending;
  const latest = d.versions[0];
  const run = (p: Parameters<typeof act.mutate>[0]) => { setErr(null); act.mutate(p); };
  const save = (q: AQuestion | null, section: SectionKind) => (draft: QuestionDraft) =>
    run(q ? { method: "patch", url: `/questions/${q.id}`, body: toBody(draft, false), ok: "Question saved. It needs approval again." } : { method: "post", url: "/questions", body: toBody({ ...draft, section }, true), ok: "Question added." });

  return (
    <>
      <PageHeader title={d.title} description={`${d.candidate_name} · ${d.opening_title}`} actions={<Link to="/assessments" className="text-sm text-brand-700 hover:underline">← All assessments</Link>} />
      <div className="mb-4 space-y-2">
        {d.ai.is_mock && <Alert kind="warning"><strong>MOCK mode.</strong> Questions come from a small curated pool or are placeholders. Set <code>AI_PROVIDER=anthropic</code> for job- and resume-specific questions.</Alert>}
        {d.generation_notes.filter((n) => !n.startsWith("MOCK")).map((n) => <Alert key={n} kind="info">{n}</Alert>)}
        <p className="text-xs text-slate-500">{d.notice}</p>
      </div>

      <Card className="mb-6 p-5">
        <div className="flex flex-wrap items-center gap-3">
          <AssessmentStatusBadge status={d.status} version={d.latest_version} unapproved={d.has_unapproved_changes} />
          {d.published_version && <Badge tone="blue">Published v{d.published_version}</Badge>}
          <span className="text-sm text-slate-600">{d.total_marks} marks · {d.duration_minutes} min · {d.counts.approved} approved, {d.counts.pending} to review, {d.counts.rejected} rejected</span>
        </div>
        {d.has_unapproved_changes && <p className="mt-2 text-sm text-amber-800">You changed this assessment after version {d.latest_version} was approved. The approved version is unchanged and stays in use until you approve the new one.</p>}
        {d.can_edit && (
          <div className="mt-4 flex flex-wrap gap-2">
            {d.counts.pending > 0 && <Button variant="secondary" loading={busy} onClick={() => run({ method: "post", url: "/questions/approve-all", ok: "Questions approved." })}>Approve all reviewed questions</Button>}
            <Button disabled={d.blockers.length > 0 || d.status === "approved"} onClick={() => { setErr(null); setDialog({ kind: "approve" }); }}>Approve assessment</Button>
            {latest && !latest.published_at && d.status === "approved" && <Button variant="secondary" loading={busy} onClick={() => run({ method: "post", url: `/versions/${latest.version}/publish`, ok: `Version ${latest.version} published.` })}>Publish v{latest.version}</Button>}
            {d.versions.length === 0 && <Button variant="ghost" onClick={() => setDialog({ kind: "deleteAll" })}>Delete draft</Button>}
          </div>
        )}
        {d.can_edit && d.blockers.length > 0 && d.status !== "approved" && (
          <ul className="mt-3 list-disc space-y-0.5 pl-5 text-sm text-slate-600">{d.blockers.map((b) => <li key={b}>{b}</li>)}</ul>
        )}
        {!d.can_edit && <p className="mt-3 text-sm text-slate-500">You can read this assessment. Approving or editing needs the “approve assessments” permission.</p>}
      
        {canSchedule && d.published_version && (
          <div className="mt-4 border-t border-slate-100 pt-4">
            <h3 className="text-sm font-semibold text-slate-900">Online test</h3>
            {activeSchedule ? (
              <p className="mt-1 text-sm text-slate-700"><ScheduleStatusBadge status={activeSchedule.status} /> <Link className="ml-2 text-brand-700 underline" to={`/schedules/${activeSchedule.id}`}>View schedule</Link></p>
            ) : (
              <div className="mt-2"><Button onClick={() => setScheduling(true)}>Schedule online test (v{d.published_version})</Button><p className="mt-1 text-xs text-slate-500">The applicant receives an email and in-app invitation. The published version is pinned; later edits do not change it.</p></div>
            )}
          </div>
        )}
      </Card>

      <div className="space-y-6">
        {d.sections.map((s: ASection) => (
          <Card key={s.id} className="p-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold text-slate-900">{s.title} <span className="ml-1 text-sm font-normal text-slate-500">{s.questions.filter((q) => q.status !== "rejected").length} questions · {s.total_marks} marks</span></h2>
              {d.can_edit && (
                <div className="flex gap-2">
                  {s.kind === "aptitude" && <Button size="sm" variant="secondary" onClick={() => setDialog({ kind: "bank" })}><Plus className="size-4" /> From bank</Button>}
                  <Button size="sm" variant="secondary" onClick={() => { setErr(null); setDialog({ kind: "add", section: s.kind }); }}><Plus className="size-4" /> Write question</Button>
                </div>
              )}
            </div>
            {s.questions.length === 0 ? <p className="text-sm text-slate-500">No questions in this section yet. Every assessment needs at least one in each section.</p> : (
              <ol className="space-y-3">
                {s.questions.map((q) => (
                  <QuestionCard key={q.id} q={q} d={d} busy={busy}
                    onApprove={() => run({ method: "post", url: `/questions/${q.id}/approve` })}
                    onReject={() => { setErr(null); setDialog({ kind: "reject", q }); }}
                    onEdit={() => { setErr(null); setDialog({ kind: "edit", q }); }}
                    onRegenerate={() => run({ method: "post", url: `/questions/${q.id}/regenerate`, ok: "Replaced with a new question. Review it." })}
                    onDelete={() => setDialog({ kind: "delete", q })} />
                ))}
              </ol>
            )}
          </Card>
        ))}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="mb-3 font-semibold text-slate-900">Approved versions</h2>
          {d.versions.length === 0 ? <p className="text-sm text-slate-500">Nothing approved yet.</p> : (
            <ul className="divide-y divide-slate-100 text-sm">
              {d.versions.map((v) => (
                <li key={v.id} className="flex items-center justify-between gap-2 py-2">
                  <span>v{v.version} · {v.total_marks} marks<span className="block text-xs text-slate-500">{v.approved_by_name} · {formatDateTime(v.approved_at)}{v.published_at ? " · published" : ""}</span></span>
                  <Button size="sm" variant="ghost" onClick={() => setDialog({ kind: "version", v: v.version })}>View</Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="p-5">
          <h2 className="mb-3 font-semibold text-slate-900">Approval history</h2>
          {d.approvals.length === 0 ? <p className="text-sm text-slate-500">No approvals yet.</p> : (
            <ul className="space-y-2 text-sm">
              {d.approvals.map((a) => (
                <li key={a.id}><strong>v{a.version}</strong> approved by {a.reviewer_name} · {formatDateTime(a.created_at)}
                  <span className="block text-xs text-slate-500">{a.changes.first_version ? `${a.question_ids.length} questions` : `${a.changes.added.length} added, ${a.changes.removed.length} removed, ${a.changes.edited.length} edited`}{a.note ? ` · “${a.note}”` : ""}</span></li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {dialog?.kind === "edit" && <QuestionEditor title="Edit question" initial={draftFrom(dialog.q)} saving={busy} error={err} onSave={save(dialog.q, dialog.q.section)} onClose={() => setDialog(null)} />}
      {dialog?.kind === "add" && <QuestionEditor title="Write a question" initial={emptyDraft(dialog.section)} saving={busy} error={err} onSave={save(null, dialog.section)} onClose={() => setDialog(null)} />}
      {dialog?.kind === "bank" && <BankPicker onClose={() => setDialog(null)} onPick={(bid) => { run({ method: "post", url: "/questions/from-bank", body: { bank_question_id: bid }, ok: "Added from the bank." }); }} />}
      {dialog?.kind === "version" && <VersionDialog id={d.id} version={dialog.v} onClose={() => setDialog(null)} />}
      {dialog?.kind === "reject" && (
        <Modal open onClose={() => setDialog(null)} title="Reject question"
          footer={<><Button variant="secondary" onClick={() => setDialog(null)}>Cancel</Button><Button variant="danger" loading={busy} onClick={() => run({ method: "post", url: `/questions/${dialog.q.id}/reject`, body: { reason: text.trim() || null } })}>Reject</Button></>}>
          <div className="space-y-3">{err && <Alert kind="error">{err}</Alert>}<Field label="Reason (optional)" htmlFor="rej"><Textarea id="rej" rows={3} maxLength={1000} value={text} onChange={(e) => setText(e.target.value)} /></Field><p className="text-xs text-slate-500">Rejected questions stay in the draft for reference but are never included in an approved version.</p></div>
        </Modal>
      )}
      {dialog?.kind === "approve" && (
        <Modal open onClose={() => setDialog(null)} title={`Approve assessment${d.latest_version ? ` (version ${d.latest_version + 1})` : ""}`}
          footer={<><Button variant="secondary" onClick={() => setDialog(null)}>Cancel</Button><Button loading={busy} onClick={() => run({ method: "post", url: "/approve", body: { note: text.trim() || null }, ok: "Assessment approved." })}>Approve</Button></>}>
          <div className="space-y-3">
            {err && <Alert kind="error">{err}</Alert>}
            <Alert kind="info">You confirm you have read every question and answer. Approving freezes a new version ({d.total_marks} marks). Applicants can only ever be tested on an approved version.</Alert>
            <Field label="Note (optional)" htmlFor="appr-note"><Textarea id="appr-note" rows={2} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} /></Field>
          </div>
        </Modal>
      )}
      <ConfirmDialog open={dialog?.kind === "delete"} title="Delete this question?" message="It is removed from the draft. Approved versions that already contain it are not affected." confirmLabel="Delete" danger loading={busy}
        onCancel={() => setDialog(null)} onConfirm={() => dialog?.kind === "delete" && run({ method: "delete", url: `/questions/${dialog.q.id}`, ok: "Question deleted." })} />
      <ConfirmDialog open={dialog?.kind === "deleteAll"} title="Delete this draft assessment?" message="All questions in it are removed. You can generate a new one afterwards." confirmLabel="Delete draft" danger loading={remove.isPending}
        onCancel={() => setDialog(null)} onConfirm={() => remove.mutate()} />
      {scheduling && <ScheduleDialog applicationId={d.application_id} durationMinutes={d.duration_minutes} onClose={() => setScheduling(false)} />}
    </>
  );
}
