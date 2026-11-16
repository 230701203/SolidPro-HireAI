import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Alert, Badge, Button, Card, ErrorState, Field, Modal, PageHeader, Spinner, Textarea, TextInput } from "@/components/ui";
import { ScheduleStatusBadge, localToIso } from "@/components/ScheduleBadge";
import ScheduleDialog from "@/components/ScheduleDialog";
import { useToast } from "@/components/Toast";
import { formatDateTime, humanize } from "@/utils/format";
import type { RecordingItem, RescheduleItem, ScheduleDetail } from "@/types";

function DecisionDialog({ schedule, req, onClose }: { schedule: ScheduleDetail; req: RescheduleItem; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [action, setAction] = useState<"approve" | "reject" | "suggest">("approve");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [comment, setComment] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => api.post(`/schedules/${schedule.id}/reschedule-requests/${req.id}`, {
      action, comment: comment || null, new_window_start: action === "reject" || !start ? null : localToIso(start), new_window_end: action === "reject" || !end ? null : localToIso(end),
    }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["schedule", schedule.id] }); void qc.invalidateQueries({ queryKey: ["schedules"] }); toast.success("Response sent to the applicant."); onClose(); },
    onError: (e) => setErr(errorMessage(e)),
  });
  return (
    <Modal open onClose={onClose} title="Respond to reschedule request"
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={m.isPending} onClick={() => { setErr(null); m.mutate(); }}>Send response</Button></>}>
      <div className="space-y-4">
        {err && <Alert kind="error">{err}</Alert>}
        <p className="rounded-md bg-slate-50 p-3 text-sm text-slate-700">“{req.reason}”{req.preferred_start && <span className="block text-xs text-slate-500">Preferred start: {formatDateTime(req.preferred_start)}</span>}</p>
        <Field label="Decision" htmlFor="dec-action">
          <select id="dec-action" className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={action} onChange={(e) => setAction(e.target.value as typeof action)}>
            <option value="approve">Approve with a new window</option><option value="suggest">Suggest a different time</option><option value="reject">Decline (keep the original window)</option>
          </select>
        </Field>
        {action !== "reject" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="New window opens" htmlFor="dec-start"><TextInput id="dec-start" type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
            <Field label="New window closes" htmlFor="dec-end"><TextInput id="dec-end" type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
          </div>
        )}
        <Field label={action === "reject" ? "Reason (required)" : "Message (optional)"} htmlFor="dec-comment"><Textarea id="dec-comment" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
      </div>
    </Modal>
  );
}

export default function ScheduleDetailPage() {
  const { id } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const [edit, setEdit] = useState(false);
  const [cancel, setCancel] = useState(false);
  const [reason, setReason] = useState("");
  const [decide, setDecide] = useState<RescheduleItem | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const { data: s, isLoading, error, refetch } = useQuery({ queryKey: ["schedule", Number(id)], queryFn: async () => (await api.get<ScheduleDetail>(`/schedules/${id}`)).data });
  const { data: recs } = useQuery({ queryKey: ["schedule-recordings", Number(id)], enabled: !!s?.attempt, queryFn: async () => (await api.get<RecordingItem[]>(`/schedules/${id}/recordings`)).data });
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["schedule", Number(id)] }); void qc.invalidateQueries({ queryKey: ["schedules"] }); };
  const resend = useMutation({
    mutationFn: async () => (await api.post<ScheduleDetail>(`/schedules/${id}/resend`)).data,
    onSuccess: (r) => { refresh(); setLink(r.invite_link); toast.success("Invitation resent. The previous link no longer works."); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const navigate = useNavigate();
  const openEval = useMutation({
    mutationFn: async () => (await api.post<{ id: number }>(`/schedules/${id}/evaluation`)).data,
    onSuccess: (r) => navigate(`/results/${r.id}`),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const doCancel = useMutation({
    mutationFn: () => api.post(`/schedules/${id}/cancel`, { reason }),
    onSuccess: () => { refresh(); setCancel(false); toast.success("Schedule cancelled."); },
    onError: (e) => setErr(errorMessage(e)),
  });

  if (isLoading) return <Spinner />;
  if (error || !s) return <Card><ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /></Card>;
  const pending = s.reschedules.filter((r) => r.status === "pending");
  const clientEvents = s.events.filter((e) => e.client_reported);
  return (
    <>
      <PageHeader title={s.candidate_name} description={`${s.opening_title} · ${s.assessment_title} (v${s.version})`} actions={<Link to="/schedules" className="text-sm text-brand-700 hover:underline">← All schedules</Link>} />
      {s.is_mock && <div className="mb-4"><Alert kind="warning"><strong>MOCK content.</strong> This assessment was generated in mock mode.</Alert></div>}
      <Card className="mb-6 p-5">
        <div className="flex flex-wrap items-center gap-3"><ScheduleStatusBadge status={s.status} />{pending.length > 0 && <Badge tone="amber">Reschedule requested</Badge>}</div>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div><dt className="text-slate-500">Window</dt><dd>{formatDateTime(s.window_start)} to {formatDateTime(s.window_end)}</dd></div>
          <div><dt className="text-slate-500">Duration</dt><dd>{s.duration_minutes} minutes once started</dd></div>
          <div><dt className="text-slate-500">Applicant</dt><dd>{s.candidate_email}</dd></div>
          <div><dt className="text-slate-500">Invitation link valid until</dt><dd>{formatDateTime(s.link_expires_at)}</dd></div>
          {s.accepted_at && <div><dt className="text-slate-500">Accepted</dt><dd>{formatDateTime(s.accepted_at)}</dd></div>}
          {s.cancel_reason && <div><dt className="text-slate-500">Cancelled</dt><dd>{s.cancel_reason}</dd></div>}
          {s.instructions && <div className="sm:col-span-2"><dt className="text-slate-500">Instructions</dt><dd className="whitespace-pre-wrap">{s.instructions}</dd></div>}
        </dl>
        {s.can_edit && (
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setEdit(true)}>Edit</Button>
            <Button variant="secondary" loading={resend.isPending} onClick={() => resend.mutate()}>Resend invitation</Button>
            <Button variant="ghost" onClick={() => { setErr(null); setCancel(true); }}>Cancel schedule</Button>
          </div>
        )}
        {link && <div className="mt-3"><Alert kind="info">New link (shown once): <code className="break-all text-xs">{link}</code></Alert></div>}
      </Card>

      {s.reschedules.length > 0 && (
        <Card className="mb-6 p-5">
          <h2 className="mb-3 text-sm font-semibold text-slate-900">Reschedule requests</h2>
          <ul className="space-y-3">
            {s.reschedules.map((r) => (
              <li key={r.id} className="rounded-md border border-slate-200 p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2"><Badge tone={r.status === "pending" ? "amber" : r.status.includes("accepted") || r.status === "approved" ? "green" : "slate"}>{humanize(r.status)}</Badge><span className="text-xs text-slate-500">{formatDateTime(r.created_at)}</span></div>
                <p className="mt-2">“{r.reason}”</p>
                {r.preferred_start && <p className="text-xs text-slate-500">Preferred start: {formatDateTime(r.preferred_start)}</p>}
                {r.comment && <p className="mt-1 text-xs text-slate-600">Response: {r.comment}</p>}
                {r.new_window_start && <p className="text-xs text-slate-600">New window: {formatDateTime(r.new_window_start)} to {formatDateTime(r.new_window_end)}</p>}
                {r.status === "pending" && <Button size="sm" className="mt-2" onClick={() => setDecide(r)}>Respond</Button>}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {s.attempt && (
        <Card className="mb-6 p-5">
          <h2 className="mb-3 text-sm font-semibold text-slate-900">Attempt</h2>
          <p className="text-sm text-slate-700">
            {s.attempt.status === "submitted" ? `Submitted ${formatDateTime(s.attempt.submitted_at)} (${s.attempt.submit_reason === "timeout" ? "time ran out" : "by the applicant"})` : `In progress, started ${formatDateTime(s.attempt.started_at)}, deadline ${formatDateTime(s.attempt.deadline_at)}`}
          </p>
          <p className="mt-1 text-sm text-slate-600">{s.attempt.answered} of {s.attempt.total_questions} questions answered · {s.attempt.recordings} spoken answers recorded</p>
          {s.attempt.status === "submitted" && (
            <div className="mt-3">
              {s.evaluation_id ? <Link to={`/results/${s.evaluation_id}`} className="text-sm font-medium text-brand-700 underline">Open evaluation</Link> : (
                <Button variant="secondary" loading={openEval.isPending} onClick={() => openEval.mutate()}>Create and open evaluation</Button>
              )}
            </div>
          )}
          <p className="mt-2 text-xs text-slate-500">Scores are advisory and nothing here is a decision about the applicant.</p>
          {recs && recs.length > 0 && (
            <div className="mt-4">
              <h3 className="mb-2 text-sm font-medium text-slate-900">Repeat the Sentence recordings</h3>
              <ul className="space-y-2">
                {recs.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-center gap-3 text-sm">
                    <span className="w-44 text-slate-600">Sentence {r.question_id} · take {r.attempt_no}</span>
                    <audio controls preload="none" src={`/api/recordings/${r.id}/file`} aria-label={`Recording for question ${r.question_id}, take ${r.attempt_no}`} />
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-slate-500">Each playback is logged. Do not judge accent; a speech score is never the sole basis for a decision.</p>
            </div>
          )}
        </Card>
      )}

      <Card className="p-5">
        <h2 className="mb-1 text-sm font-semibold text-slate-900">Activity</h2>
        {clientEvents.length > 0 && <p className="mb-3 text-xs text-slate-500">{clientEvents.length} browser event(s) were reported during the test (tab switches, copy/paste, connection drops). They are context only and never grounds for automatic rejection; connection or accessibility problems are common.</p>}
        <ul className="space-y-1 text-sm">
          {s.events.map((e) => (
            <li key={e.id} className="flex justify-between gap-3 border-b border-slate-100 py-1"><span className={e.client_reported ? "text-slate-500" : "text-slate-800"}>{humanize(e.kind.replace("client_", "browser: "))}</span><span className="shrink-0 text-xs text-slate-500">{formatDateTime(e.created_at)}</span></li>
          ))}
        </ul>
      </Card>

      {edit && <ScheduleDialog applicationId={s.application_id} existing={s} durationMinutes={s.duration_minutes} onClose={() => setEdit(false)} onDone={(r) => { if (r.invite_link) setLink(r.invite_link); }} />}
      {decide && <DecisionDialog schedule={s} req={decide} onClose={() => setDecide(null)} />}
      <Modal open={cancel} onClose={() => setCancel(false)} title="Cancel this schedule"
        footer={<><Button variant="secondary" onClick={() => setCancel(false)}>Keep it</Button><Button variant="danger" loading={doCancel.isPending} disabled={reason.trim().length < 3} onClick={() => { setErr(null); doCancel.mutate(); }}>Cancel schedule</Button></>}>
        <div className="space-y-3">{err && <Alert kind="error">{err}</Alert>}<p className="text-sm text-slate-600">The applicant is notified with your reason.</p>
          <Field label="Reason" htmlFor="cancel-reason"><Textarea id="cancel-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} /></Field></div>
      </Modal>
    </>
  );
}
