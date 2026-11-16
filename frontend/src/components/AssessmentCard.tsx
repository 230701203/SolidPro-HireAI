import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import { Alert, Button, Card, Field, Modal, Select, TextInput } from "@/components/ui";
import { AssessmentStatusBadge } from "@/pages/assessments/AssessmentsPage";
import { useAuth } from "@/contexts/AuthContext";
import type { AssessmentDetail, AssessmentListItem, Difficulty, Page } from "@/types";

function GenerateDialog({ applicationId, onClose }: { applicationId: number; onClose: () => void }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [duration, setDuration] = useState(45);
  const [counts, setCounts] = useState({ mcq_count: 10, aptitude_count: 6, rs_count: 5 });
  const [err, setErr] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: async () => (await api.post<AssessmentDetail>("/assessments", { application_id: applicationId, difficulty, duration_minutes: duration, config: counts })).data,
    onSuccess: (d) => { void qc.invalidateQueries({ queryKey: ["assessments"] }); navigate(`/assessments/${d.id}`); },
    onError: (e) => setErr(errorMessage(e)),
  });
  const num = (k: keyof typeof counts, max: number) => (e: React.ChangeEvent<HTMLInputElement>) => setCounts((c) => ({ ...c, [k]: Math.max(1, Math.min(max, Number(e.target.value) || 1)) }));
  return (
    <Modal open onClose={onClose} title="Generate assessment"
      footer={<><Button variant="secondary" onClick={onClose} disabled={run.isPending}>Cancel</Button><Button loading={run.isPending} onClick={() => { setErr(null); run.mutate(); }}>Generate draft</Button></>}>
      <div className="space-y-4">
        {err && <Alert kind="error">{err}</Alert>}
        <Alert kind="info">This creates a draft with three sections: MCQ, Aptitude and Repeat the Sentence. Nothing is visible to the applicant until you review and approve it.</Alert>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Difficulty" htmlFor="g-diff"><Select id="g-diff" value={difficulty} onChange={(e) => setDifficulty(e.target.value as Difficulty)}><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></Select></Field>
          <Field label="Duration (minutes)" htmlFor="g-dur"><TextInput id="g-dur" type="number" min={10} max={240} value={duration} onChange={(e) => setDuration(Math.max(10, Math.min(240, Number(e.target.value) || 10)))} /></Field>
          <Field label="MCQ questions" htmlFor="g-mcq"><TextInput id="g-mcq" type="number" min={1} max={40} value={counts.mcq_count} onChange={num("mcq_count", 40)} /></Field>
          <Field label="Aptitude questions" htmlFor="g-apt"><TextInput id="g-apt" type="number" min={1} max={30} value={counts.aptitude_count} onChange={num("aptitude_count", 30)} /></Field>
          <Field label="Repeat the Sentence items" htmlFor="g-rs"><TextInput id="g-rs" type="number" min={1} max={15} value={counts.rs_count} onChange={num("rs_count", 15)} /></Field>
        </div>
      </div>
    </Modal>
  );
}

/** Shown on an application that was approved for assessment, to staff who may generate or review assessments. */
export default function AssessmentCard({ applicationId }: { applicationId: number }) {
  const { hasPermission } = useAuth();
  const canGenerate = hasPermission("generate_assessments");
  const canSee = canGenerate || hasPermission("approve_assessments");
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["assessments", "for-application", applicationId], enabled: canSee,
    queryFn: async () => (await api.get<Page<AssessmentListItem>>("/assessments", { params: { application_id: applicationId, page_size: 1 } })).data,
  });
  if (!canSee || isLoading) return null;
  const existing = data?.items[0];
  return (
    <Card className="p-5">
      <h2 className="mb-2 flex items-center gap-2 font-semibold text-slate-900"><ClipboardCheck className="size-4 text-brand-600" aria-hidden /> Assessment</h2>
      {existing ? (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <AssessmentStatusBadge status={existing.status} version={existing.latest_version} />
          <span className="text-slate-600">{existing.question_count} questions · {existing.total_marks} marks</span>
          <Link to={`/assessments/${existing.id}`} className="font-medium text-brand-700 hover:underline">Open assessment</Link>
        </div>
      ) : canGenerate ? (
        <>
          <p className="mb-3 text-sm text-slate-600">This applicant was approved for assessment. Generate a draft, then review and approve it before anything is scheduled.</p>
          <Button onClick={() => setOpen(true)}>Generate assessment</Button>
        </>
      ) : <p className="text-sm text-slate-500">No assessment has been generated yet.</p>}
      {open && <GenerateDialog applicationId={applicationId} onClose={() => setOpen(false)} />}
    </Card>
  );
}
