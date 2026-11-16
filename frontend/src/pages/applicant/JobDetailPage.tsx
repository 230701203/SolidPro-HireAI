import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Alert, Badge, Button, Card, ErrorState, Field, Modal, PageHeader, Spinner, Textarea } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { formatDate } from "@/utils/format";
import { EMPLOYMENT_LABELS, WORK_MODE_LABELS } from "@/utils/labels";
import type { ApplicationDetail, Profile, PublicJob } from "@/types";

function ApplyDialog({ job, profile, onClose }: { job: PublicJob; profile: Profile; onClose: () => void }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const current = profile.resumes.find((r) => r.is_current) ?? profile.resumes[0];
  const m = useMutation({
    mutationFn: async () => (await api.post<ApplicationDetail>("/applications", { opening_id: job.id, resume_id: current?.id ?? null, cover_note: note.trim() || null })).data,
    onSuccess: (d) => { toast.success("Application submitted."); void qc.invalidateQueries({ queryKey: ["jobs"] }); void qc.invalidateQueries({ queryKey: ["job", String(job.id)] }); void qc.invalidateQueries({ queryKey: ["my-applications"] }); navigate(`/my-applications/${d.id}`); },
    onError: (e) => setErr(errorMessage(e)),
  });
  return (
    <Modal open onClose={onClose} title={`Apply for ${job.title}`}
      footer={<><Button variant="secondary" onClick={onClose} disabled={m.isPending}>Cancel</Button><Button loading={m.isPending} onClick={() => { setErr(null); m.mutate(); }}>Submit application</Button></>}>
      <div className="space-y-4">
        {err && <Alert kind="error">{err}</Alert>}
        <p className="text-sm text-slate-600">Resume that will be attached: <strong>{current?.original_filename}</strong> (version {current?.version}).</p>
        <Field label="Cover note (optional)" htmlFor="cover"><Textarea id="cover" rows={4} maxLength={3000} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      </div>
    </Modal>
  );
}

export default function JobDetailPage() {
  const { id } = useParams();
  const [applying, setApplying] = useState(false);
  const job = useQuery({ queryKey: ["job", id], queryFn: async () => (await api.get<PublicJob>(`/jobs/${id}`)).data });
  const profile = useQuery({ queryKey: ["my-profile"], queryFn: async () => (await api.get<Profile>("/applicants/profile")).data });
  if (job.isLoading || profile.isLoading) return <Spinner />;
  if (job.error || !job.data) return <Card><ErrorState message={errorMessage(job.error)} onRetry={() => void job.refetch()} /></Card>;
  const j = job.data;
  const p = profile.data;
  const ready = !!p && !!p.mobile && p.education.length > 0 && p.resumes.length > 0;
  const missing = p ? [!p.mobile && "mobile number", p.education.length === 0 && "an education entry", p.resumes.length === 0 && "a resume"].filter(Boolean) as string[] : [];
  return (
    <>
      <PageHeader title={j.title} description={`${j.category_name} · ${EMPLOYMENT_LABELS[j.employment_type]} · ${WORK_MODE_LABELS[j.work_mode]}${j.location ? ` · ${j.location}` : ""}`}
        actions={<Link to="/jobs" className="text-sm text-brand-700 hover:underline">← All jobs</Link>} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="space-y-5 p-5 lg:col-span-2">
          <div><h3 className="mb-1 text-sm font-semibold">About the role</h3><p className="whitespace-pre-line text-sm text-slate-700">{j.description}</p></div>
          {j.responsibilities && <div><h3 className="mb-1 text-sm font-semibold">Responsibilities</h3><p className="whitespace-pre-line text-sm text-slate-700">{j.responsibilities}</p></div>}
          <div><h3 className="mb-1.5 text-sm font-semibold">Required skills</h3><div className="flex flex-wrap gap-1.5">{j.required_skills.map((s) => <Badge key={s} tone="blue">{s}</Badge>)}</div></div>
          {j.preferred_skills.length > 0 && <div><h3 className="mb-1.5 text-sm font-semibold">Preferred skills</h3><div className="flex flex-wrap gap-1.5">{j.preferred_skills.map((s) => <Badge key={s}>{s}</Badge>)}</div></div>}
          {j.required_qualifications && <div><h3 className="mb-1 text-sm font-semibold">Qualifications</h3><p className="whitespace-pre-line text-sm text-slate-700">{j.required_qualifications}</p></div>}
          {j.is_internship && (
            <div className="rounded-lg bg-slate-50 p-3 text-sm"><h3 className="mb-1 font-semibold">Internship details</h3>
              {[["Duration", j.intern_duration], ["Availability", j.intern_availability], ["Stipend", j.intern_stipend]].map(([k, v]) => v ? <p key={k}><span className="text-slate-500">{k}:</span> {v}</p> : null)}
            </div>
          )}
        </Card>
        <Card className="h-fit space-y-3 p-5">
          <p className="text-sm text-slate-600">Vacancies: {j.vacancies}</p>
          {j.deadline && <p className="text-sm text-slate-600">Apply by {formatDate(j.deadline)}</p>}
          {j.applied ? (
            <><Alert kind="success">You have applied to this opening.</Alert>{j.application_id && <Link to={`/my-applications/${j.application_id}`} className="block text-sm font-medium text-brand-700 hover:underline">View my application</Link>}</>
          ) : ready ? (
            <Button className="w-full" onClick={() => setApplying(true)}>Apply now</Button>
          ) : (
            <><Alert kind="warning">Before applying, add {missing.join(", ")}.</Alert><Link to="/applicant/profile" className="block text-sm font-medium text-brand-700 hover:underline">Complete my profile</Link></>
          )}
        </Card>
      </div>
      {applying && p && <ApplyDialog job={j} profile={p} onClose={() => setApplying(false)} />}
    </>
  );
}
