import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Alert, Badge, Button, Card, ErrorState, Field, Modal, PageHeader, Select, Spinner, Textarea } from "@/components/ui";
import InterviewDialog from "@/components/InterviewDialog";
import { useToast } from "@/components/Toast";
import { formatDateTime } from "@/utils/format";
import { INTERVIEW_TONE } from "./InterviewsPage";
import type { InterviewFeedback, InterviewItem } from "@/types";

const REC = [["strong_yes", "Strong yes"], ["yes", "Yes"], ["neutral", "Neutral"], ["no", "No"], ["strong_no", "Strong no"]];

export default function InterviewDetailPage() {
  const { id } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const [edit, setEdit] = useState(false);
  const [cancel, setCancel] = useState(false);
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [fb, setFb] = useState<InterviewFeedback | null>(null);

  const { data: iv, isLoading, error, refetch } = useQuery({ queryKey: ["interview", Number(id)], queryFn: async () => (await api.get<InterviewItem>(`/interviews/${id}`)).data });
  const form: InterviewFeedback = fb ?? iv?.feedback ?? { technical_feedback: "", communication_feedback: "", strengths: "", improvements: "", recommendation: "neutral" };
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["interview", Number(id)] }); void qc.invalidateQueries({ queryKey: ["interviews"] }); };
  const saveFb = useMutation({ mutationFn: () => api.put(`/interviews/${id}/feedback`, form), onSuccess: () => { refresh(); toast.success("Feedback saved."); }, onError: (e) => setErr(errorMessage(e)) });
  const complete = useMutation({ mutationFn: () => api.post(`/interviews/${id}/complete`), onSuccess: () => { refresh(); toast.success("Marked complete."); }, onError: (e) => setErr(errorMessage(e)) });
  const doCancel = useMutation({ mutationFn: () => api.post(`/interviews/${id}/cancel`, { reason }), onSuccess: () => { refresh(); setCancel(false); toast.success("Interview cancelled."); }, onError: (e) => setErr(errorMessage(e)) });

  if (isLoading) return <Spinner />;
  if (error || !iv) return <Card><ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /></Card>;
  const set = (k: keyof InterviewFeedback, v: string) => setFb({ ...form, [k]: v });
  return (
    <>
      <PageHeader title={iv.candidate_name} description={`${iv.opening_title} · ${iv.interview_type} interview`} actions={<Link to="/interviews" className="text-sm text-brand-700 hover:underline">← All interviews</Link>} />
      {err && <div className="mb-4"><Alert kind="error">{err}</Alert></div>}
      <Card className="mb-6 p-5">
        <div className="flex items-center gap-3"><Badge tone={INTERVIEW_TONE[iv.status]}>{iv.status}</Badge></div>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div><dt className="text-slate-500">When</dt><dd>{iv.scheduled_start ? `${formatDateTime(iv.scheduled_start)} (${iv.duration_minutes} min)` : "Not set yet"}</dd></div>
          <div><dt className="text-slate-500">Interviewer</dt><dd>{iv.interviewer?.full_name ?? "Unassigned"}</dd></div>
          <div><dt className="text-slate-500">Mode</dt><dd className="capitalize">{iv.mode}</dd></div>
          {iv.meeting_link && <div><dt className="text-slate-500">Meeting link</dt><dd className="break-all">{iv.meeting_link}</dd></div>}
          {iv.location && <div><dt className="text-slate-500">Location</dt><dd>{iv.location}</dd></div>}
          {iv.instructions && <div className="sm:col-span-2"><dt className="text-slate-500">Instructions for the applicant</dt><dd className="whitespace-pre-wrap">{iv.instructions}</dd></div>}
          {iv.cancel_reason && <div className="sm:col-span-2"><dt className="text-slate-500">Cancelled</dt><dd>{iv.cancel_reason}</dd></div>}
        </dl>
        <div className="mt-4 flex flex-wrap gap-2">
          {iv.can_manage && <><Button variant="secondary" onClick={() => setEdit(true)}>Edit or reschedule</Button><Button variant="ghost" onClick={() => { setErr(null); setCancel(true); }}>Cancel interview</Button></>}
          {iv.can_give_feedback && iv.status !== "completed" && <Button variant="secondary" loading={complete.isPending} onClick={() => complete.mutate()}>Mark complete</Button>}
          <Link to={`/results?search=${encodeURIComponent(iv.candidate_name)}`} className="self-center text-sm text-brand-700 underline">Candidate results</Link>
        </div>
      </Card>

      {iv.can_give_feedback && (
        <Card className="p-5">
          <h2 className="text-sm font-semibold text-slate-900">Interviewer feedback</h2>
          <p className="mb-3 text-xs text-slate-500">Internal only. Applicants never see this. Base it on the interview itself; do not comment on accent, age, gender or other personal characteristics.</p>
          <div className="space-y-3">
            <Field label="Technical feedback" htmlFor="fb-tech"><Textarea id="fb-tech" rows={3} value={form.technical_feedback ?? ""} onChange={(e) => set("technical_feedback", e.target.value)} /></Field>
            <Field label="Communication feedback" htmlFor="fb-comm"><Textarea id="fb-comm" rows={3} value={form.communication_feedback ?? ""} onChange={(e) => set("communication_feedback", e.target.value)} /></Field>
            <Field label="Strengths" htmlFor="fb-str"><Textarea id="fb-str" rows={2} value={form.strengths ?? ""} onChange={(e) => set("strengths", e.target.value)} /></Field>
            <Field label="Areas for improvement" htmlFor="fb-imp"><Textarea id="fb-imp" rows={2} value={form.improvements ?? ""} onChange={(e) => set("improvements", e.target.value)} /></Field>
            <Field label="Overall recommendation" htmlFor="fb-rec"><Select id="fb-rec" value={form.recommendation} onChange={(e) => set("recommendation", e.target.value)}>{REC.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
            <Button loading={saveFb.isPending} onClick={() => { setErr(null); saveFb.mutate(); }}>{iv.feedback ? "Update feedback" : "Save feedback and complete"}</Button>
            {iv.feedback?.submitted_by && <span className="ml-3 text-xs text-slate-500">Last saved by {iv.feedback.submitted_by}</span>}
          </div>
        </Card>
      )}
      {edit && <InterviewDialog existing={iv} onClose={() => setEdit(false)} />}
      <Modal open={cancel} onClose={() => setCancel(false)} title="Cancel this interview"
        footer={<><Button variant="secondary" onClick={() => setCancel(false)}>Keep it</Button><Button variant="danger" loading={doCancel.isPending} disabled={reason.trim().length < 3} onClick={() => doCancel.mutate()}>Cancel interview</Button></>}>
        <div className="space-y-3"><p className="text-sm text-slate-600">The applicant is notified with your reason.</p><Field label="Reason" htmlFor="iv-cancel"><Textarea id="iv-cancel" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} /></Field></div>
      </Modal>
    </>
  );
}
