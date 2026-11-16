import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Alert, Badge, Button, Card, ErrorState, Field, Modal, PageHeader, Spinner, Textarea, TextInput } from "@/components/ui";
import { ScheduleStatusBadge, localToIso } from "@/components/ScheduleBadge";
import { useToast } from "@/components/Toast";
import { formatDateTime, humanize } from "@/utils/format";
import type { Invitation, TakeAttempt } from "@/types";

export const sessionKey = (attemptId: number) => `hireai-attempt-session-${attemptId}`;

export default function MyTestDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [consent, setConsent] = useState(false);
  const [resched, setResched] = useState(false);
  const [reason, setReason] = useState("");
  const [preferred, setPreferred] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const { data: t, isLoading, error, refetch } = useQuery({ queryKey: ["my-test", Number(id)], queryFn: async () => (await api.get<Invitation>(`/test-invitations/${id}`)).data });
  const set = (d: Invitation) => { qc.setQueryData(["my-test", Number(id)], d); void qc.invalidateQueries({ queryKey: ["my-tests"] }); };

  const accept = useMutation({ mutationFn: async () => (await api.post<Invitation>(`/test-invitations/${id}/accept`)).data, onSuccess: (d) => { set(d); toast.success("Invitation accepted."); }, onError: (e) => setErr(errorMessage(e)) });
  const request = useMutation({
    mutationFn: async () => (await api.post<Invitation>(`/test-invitations/${id}/reschedule`, { reason, preferred_start: preferred ? localToIso(preferred) : null })).data,
    onSuccess: (d) => { set(d); setResched(false); setReason(""); toast.success("Request sent to the recruitment team."); },
    onError: (e) => setErr(errorMessage(e)),
  });
  const respond = useMutation({
    mutationFn: async (v: { rid: number; accept: boolean }) => (await api.post<Invitation>(`/test-invitations/${id}/reschedule/${v.rid}/respond`, { accept: v.accept })).data,
    onSuccess: set, onError: (e) => setErr(errorMessage(e)),
  });
  const start = useMutation({
    mutationFn: async () => (await api.post<TakeAttempt>(`/test-invitations/${id}/start`, { consent })).data,
    onSuccess: (a) => {
      try { sessionStorage.setItem(sessionKey(a.id), a.session_id ?? ""); } catch { /* private mode: the runner will ask to resume from here */ }
      navigate(`/take/${a.id}`);
    },
    onError: (e) => { setErr(errorMessage(e)); void refetch(); },
  });

  if (isLoading) return <Spinner />;
  if (error || !t) return <Card><ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /></Card>;
  const resuming = t.status === "in_progress";
  const suggested = t.reschedules.filter((r) => r.status === "alternative_suggested");
  return (
    <>
      <PageHeader title={t.opening_title} description="Online assessment" actions={<Link to="/my-tests" className="text-sm text-brand-700 hover:underline">← My tests</Link>} />
      {err && <div className="mb-4"><Alert kind="error">{err}</Alert></div>}
      <Card className="mb-6 p-5">
        <div className="flex flex-wrap items-center gap-3"><ScheduleStatusBadge status={t.status} /><span className="text-sm text-slate-600">{t.assessment_title}</span></div>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div><dt className="text-slate-500">Test window</dt><dd>{formatDateTime(t.window_start)} to {formatDateTime(t.window_end)}</dd></div>
          <div><dt className="text-slate-500">Time allowed</dt><dd>{t.duration_minutes} minutes once you start. The timer cannot be paused.</dd></div>
          <div className="sm:col-span-2"><dt className="text-slate-500">Sections</dt><dd>{t.sections.map((s) => `${s.title} (${s.questions})`).join(" · ")}</dd></div>
          {t.instructions && <div className="sm:col-span-2"><dt className="text-slate-500">Note from the recruitment team</dt><dd className="whitespace-pre-wrap">{t.instructions}</dd></div>}
        </dl>
      </Card>

      {suggested.map((r) => (
        <Card key={r.id} className="mb-6 border-amber-300 p-5">
          <h2 className="text-sm font-semibold text-slate-900">A different time was suggested</h2>
          <p className="mt-1 text-sm text-slate-700">{formatDateTime(r.new_window_start)} to {formatDateTime(r.new_window_end)}{r.comment && <span className="block text-slate-500">“{r.comment}”</span>}</p>
          <div className="mt-3 flex gap-2"><Button loading={respond.isPending} onClick={() => respond.mutate({ rid: r.id, accept: true })}>Accept new time</Button><Button variant="secondary" disabled={respond.isPending} onClick={() => respond.mutate({ rid: r.id, accept: false })}>Decline</Button></div>
        </Card>
      ))}

      {t.has_repeat_sentence && (
        <Card className="mb-6 p-5">
          <h2 className="text-sm font-semibold text-slate-900">Before you start: the speaking section</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
            <li>You will hear sentences and repeat them aloud. Your voice is recorded and stored privately; only authorised recruiters can listen.</li>
            <li>You can hear each sentence {(t.rs_max_replays ?? 0) + 1} time(s) and record up to {t.rs_max_attempts ?? 1} time(s), for at most {t.rs_record_seconds ?? 20} seconds each.</li>
            <li>Allow microphone access when your browser asks. Use a quiet place and a stable connection. Speak naturally; accent is not penalised.</li>
            <li>Tab switches, copy and paste, and connection drops are noted for context only. They never fail or reject you automatically.</li>
          </ul>
        </Card>
      )}

      <Card className="p-5">
        {t.can_accept && <div className="mb-4"><Button loading={accept.isPending} onClick={() => { setErr(null); accept.mutate(); }}>Accept invitation</Button></div>}
        {(t.can_start || resuming) && (
          <div className="space-y-3">
            <label className="flex items-start gap-2 text-sm text-slate-700">
              <input type="checkbox" className="mt-0.5 size-4" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              <span>I understand the test is timed, my answers and spoken recordings are stored for assessment, and I agree to these conditions.</span>
            </label>
            <Button disabled={!consent} loading={start.isPending} onClick={() => { setErr(null); start.mutate(); }}>{resuming ? "Resume test" : "Start test"}</Button>
          </div>
        )}
        {!t.can_start && !resuming && t.start_blocked_reason && t.status !== "invited" && <p className="text-sm text-slate-600">{t.start_blocked_reason}</p>}
        {t.can_request_reschedule && <div className="mt-4"><Button variant="secondary" onClick={() => { setErr(null); setResched(true); }}>Request a different time</Button></div>}
      </Card>

      {t.reschedules.length > 0 && (
        <Card className="mt-6 p-5">
          <h2 className="mb-2 text-sm font-semibold text-slate-900">Your reschedule requests</h2>
          <ul className="space-y-2 text-sm">{t.reschedules.map((r) => <li key={r.id}><Badge tone={r.status === "pending" ? "amber" : "slate"}>{humanize(r.status)}</Badge> <span className="text-slate-700">{r.reason}</span>{r.comment && <span className="block text-xs text-slate-500">Response: {r.comment}</span>}</li>)}</ul>
        </Card>
      )}

      <Modal open={resched} onClose={() => setResched(false)} title="Request a different time"
        footer={<><Button variant="secondary" onClick={() => setResched(false)}>Cancel</Button><Button loading={request.isPending} disabled={reason.trim().length < 5} onClick={() => { setErr(null); request.mutate(); }}>Send request</Button></>}>
        <div className="space-y-4">
          <p className="text-sm text-slate-600">Your current time stays in place until the team approves a change.</p>
          <Field label="Reason" htmlFor="rs-reason"><Textarea id="rs-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
          <Field label="Preferred start (optional)" htmlFor="rs-pref"><TextInput id="rs-pref" type="datetime-local" value={preferred} onChange={(e) => setPreferred(e.target.value)} /></Field>
        </div>
      </Modal>
    </>
  );
}
