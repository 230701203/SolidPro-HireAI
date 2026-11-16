import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Pagination, Select, Spinner, TableWrap, td, th } from "@/components/ui";
import { formatDate } from "@/utils/format";
import type { AssessmentListItem, Page } from "@/types";

export function AssessmentStatusBadge({ status, version, unapproved }: { status: "draft" | "approved"; version: number | null; unapproved?: boolean }) {
  if (status === "approved") return <Badge tone="green">Approved{version ? ` v${version}` : ""}</Badge>;
  return <Badge tone="amber">{unapproved || version ? `Draft (changes since v${version})` : "Draft, not approved"}</Badge>;
}

export default function AssessmentsPage() {
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [status]);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["assessments", status, page],
    queryFn: async () => (await api.get<Page<AssessmentListItem>>("/assessments", { params: { status: status || undefined, page, page_size: 15 } })).data,
  });
  return (
    <>
      <PageHeader title="Assessments" description="Review AI-drafted assessments and approve them. Nothing reaches an applicant without human approval. Create one from an approved application." />
      <Card>
        <div className="border-b border-slate-200 p-4">
          <Select aria-label="Filter by status" className="w-full sm:w-52" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option><option value="draft">Draft</option><option value="approved">Approved</option>
          </Select>
        </div>
        {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.items.length === 0 ? (
          <EmptyState title="No assessments yet" description="Open an application that is approved for assessment and choose “Generate assessment”." action={<Link to="/applications?status=approved" className="text-sm font-medium text-brand-700 hover:underline">View approved applications</Link>} />
        ) : (
          <>
            <TableWrap>
              <thead><tr><th className={th}>Assessment</th><th className={th}>Status</th><th className={th}>Questions</th><th className={th}>Marks</th><th className={th}>Published</th><th className={th}>Created</th></tr></thead>
              <tbody>
                {data.items.map((a) => (
                  <tr key={a.id} className="hover:bg-slate-50/60">
                    <td className={td}><Link to={`/assessments/${a.id}`} className="font-medium text-slate-900 hover:underline">{a.title}</Link><span className="block text-xs text-slate-500">{a.candidate_name} · {a.opening_title}{a.is_mock && " · MOCK"}</span></td>
                    <td className={td}><AssessmentStatusBadge status={a.status} version={a.latest_version} /></td>
                    <td className={`${td} tabular-nums`}>{a.question_count}{a.pending_count > 0 && <span className="ml-1 text-xs text-amber-700">({a.pending_count} to review)</span>}</td>
                    <td className={`${td} tabular-nums`}>{a.total_marks}</td>
                    <td className={td}>{a.published_version ? `v${a.published_version}` : "—"}</td>
                    <td className={td}>{formatDate(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={data.page_size} onPage={setPage} />
          </>
        )}
      </Card>
    </>
  );
}
