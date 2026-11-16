import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Pencil, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import { Alert, Badge, Button, Card, ConfirmDialog, ErrorState, PageHeader, Spinner } from "@/components/ui";
import { OpeningStatusBadge, ApplicationStatusBadge } from "@/components/badges";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/components/Toast";
import { formatDate } from "@/utils/format";
import { EMPLOYMENT_LABELS, WORK_MODE_LABELS } from "@/utils/labels";
import type { ApplicationListItem, Opening, Page } from "@/types";

type Action = "publish" | "unpublish" | "close" | "delete" | null;

const COPY: Record<Exclude<Action, null>, { title: string; message: string; label: string; danger?: boolean }> = {
  publish: { title: "Publish this opening?", message: "It becomes visible to applicants and they can start applying.", label: "Publish" },
  unpublish: { title: "Move back to draft?", message: "Applicants will no longer see this opening. Existing applications are kept.", label: "Unpublish" },
  close: { title: "Close this opening?", message: "No new applications will be accepted. Existing applications stay available for review.", label: "Close opening" },
  delete: { title: "Delete this opening?", message: "This cannot be undone. Openings that already have applications cannot be deleted.", label: "Delete", danger: true },
};

function Section({ title, children }: { title: string; children?: React.ReactNode }) {
  if (!children) return null;
  return <div><h3 className="mb-1 text-sm font-semibold text-slate-900">{title}</h3><div className="whitespace-pre-line text-sm text-slate-700">{children}</div></div>;
}

function Tags({ items, tone }: { items: string[]; tone: "blue" | "slate" }) {
  return items.length ? <div className="flex flex-wrap gap-1.5">{items.map((s) => <Badge key={s} tone={tone}>{s}</Badge>)}</div> : null;
}

export default function OpeningDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const { hasPermission } = useAuth();
  const canManage = hasPermission("manage_job_openings");
  const [action, setAction] = useState<Action>(null);

  const { data: o, isLoading, error, refetch } = useQuery({ queryKey: ["opening", id], queryFn: async () => (await api.get<Opening>(`/job-openings/${id}`)).data });
  const apps = useQuery({
    queryKey: ["opening-apps", id],
    enabled: hasPermission("review_applications"),
    queryFn: async () => (await api.get<Page<ApplicationListItem>>(`/job-openings/${id}/applications`, { params: { page_size: 8 } })).data,
  });

  const run = useMutation({
    mutationFn: async (a: Exclude<Action, null>) => (a === "delete" ? api.delete(`/job-openings/${id}`) : api.post(`/job-openings/${id}/${a}`)),
    onSuccess: (_d, a) => {
      void qc.invalidateQueries({ queryKey: ["openings"] });
      void qc.invalidateQueries({ queryKey: ["opening", id] });
      setAction(null);
      if (a === "delete") { toast.success("Opening deleted."); navigate("/openings"); } else toast.success("Opening updated.");
    },
    onError: (e) => { setAction(null); toast.error(errorMessage(e)); },
  });
  const duplicate = useMutation({
    mutationFn: async () => (await api.post<Opening>(`/job-openings/${id}/duplicate`)).data,
    onSuccess: (d) => { void qc.invalidateQueries({ queryKey: ["openings"] }); toast.success("Copied as a new draft."); navigate(`/openings/${d.id}`); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (isLoading) return <Spinner />;
  if (error || !o) return <Card><ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /></Card>;

  return (
    <>
      <PageHeader
        title={o.title}
        description={`${o.category_name} · ${EMPLOYMENT_LABELS[o.employment_type]} · ${WORK_MODE_LABELS[o.work_mode]}${o.location ? ` · ${o.location}` : ""}`}
        actions={canManage && (
          <div className="flex flex-wrap gap-2">
            {o.status === "draft" && <Button onClick={() => setAction("publish")}>Publish</Button>}
            {o.status === "published" && <Button variant="secondary" onClick={() => setAction("unpublish")}>Unpublish</Button>}
            {o.status === "published" && <Button variant="secondary" onClick={() => setAction("close")}>Close</Button>}
            <Button variant="secondary" onClick={() => navigate(`/openings/${o.id}/edit`)}><Pencil className="size-4" /> Edit</Button>
            <Button variant="secondary" loading={duplicate.isPending} onClick={() => duplicate.mutate()}><Copy className="size-4" /> Duplicate</Button>
            <Button variant="danger" onClick={() => setAction("delete")}><Trash2 className="size-4" /> Delete</Button>
          </div>
        )}
      />
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm text-slate-600">
        <OpeningStatusBadge status={o.status} open={o.is_open} />
        <span>Vacancies: {o.vacancies}</span><span>Deadline: {formatDate(o.deadline)}</span>
        {o.published_at && <span>Published {formatDate(o.published_at)}</span>}
        {o.created_by_name && <span>Created by {o.created_by_name}</span>}
      </div>
      {o.status === "published" && !o.is_open && <div className="mb-4"><Alert kind="warning">The deadline has passed, so applicants can no longer apply.</Alert></div>}
      {o.status === "draft" && <div className="mb-4"><Alert kind="info">This is a draft. Applicants cannot see it until it is published.</Alert></div>}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="space-y-5 p-5 lg:col-span-2">
          <Section title="Description">{o.description}</Section>
          <Section title="Responsibilities">{o.responsibilities}</Section>
          <div><h3 className="mb-1.5 text-sm font-semibold text-slate-900">Required skills</h3><Tags items={o.required_skills} tone="blue" /></div>
          {o.preferred_skills.length > 0 && <div><h3 className="mb-1.5 text-sm font-semibold text-slate-900">Preferred skills</h3><Tags items={o.preferred_skills} tone="slate" /></div>}
          <Section title="Required qualifications">{o.required_qualifications}</Section>
          <Section title="Preferred qualifications">{o.preferred_qualifications}</Section>
          <Section title="Required experience">{o.required_experience}</Section>
          {o.category_is_internship && (
            <div className="rounded-lg bg-slate-50 p-3 text-sm">
              <h3 className="mb-1 font-semibold text-slate-900">Internship details</h3>
              <dl className="grid grid-cols-[8rem_1fr] gap-y-1">
                {([["College", o.intern_college], ["Degree", o.intern_degree], ["Department", o.intern_department], ["Graduation year", o.intern_graduation_year], ["Duration", o.intern_duration], ["Availability", o.intern_availability], ["Stipend", o.intern_stipend]] as const).map(([k, v]) => v ? <div key={k} className="contents"><dt className="text-slate-500">{k}</dt><dd>{v}</dd></div> : null)}
              </dl>
            </div>
          )}
        </Card>
        <div className="space-y-6">
          <Card className="p-5">
            <h3 className="mb-2 text-sm font-semibold text-slate-900">Assigned recruiters</h3>
            {o.assignees.length === 0 ? <p className="text-sm text-slate-500">Nobody assigned yet.</p> : <ul className="space-y-1 text-sm">{o.assignees.map((a) => <li key={a.id}>{a.full_name}<span className="block text-xs text-slate-500">{a.email}</span></li>)}</ul>}
          </Card>
          {hasPermission("review_applications") && (
            <Card className="p-5">
              <div className="mb-2 flex items-center justify-between"><h3 className="text-sm font-semibold text-slate-900">Applications ({o.applications_count})</h3><Link className="text-xs text-brand-700 hover:underline" to={`/applications?opening_id=${o.id}`}>View all</Link></div>
              {apps.isLoading ? <Spinner /> : apps.data?.items.length ? (
                <ul className="divide-y divide-slate-100 text-sm">
                  {apps.data.items.map((a) => (
                    <li key={a.id} className="flex items-center justify-between gap-2 py-2">
                      <Link to={`/applications/${a.id}`} className="min-w-0 truncate font-medium hover:underline">{a.candidate_name}</Link>
                      <ApplicationStatusBadge status={a.status} />
                    </li>
                  ))}
                </ul>
              ) : <p className="text-sm text-slate-500">No applications yet.</p>}
            </Card>
          )}
        </div>
      </div>

      {action && (
        <ConfirmDialog open title={COPY[action].title} message={COPY[action].message} confirmLabel={COPY[action].label} danger={COPY[action].danger} loading={run.isPending} onCancel={() => setAction(null)} onConfirm={() => run.mutate(action)} />
      )}
    </>
  );
}
