import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Pagination, Select, Spinner, TableWrap, td, th } from "@/components/ui";
import { formatDateTime } from "@/utils/format";
import type { InterviewItem, InterviewStatus, Page } from "@/types";

export const INTERVIEW_TONE: Record<InterviewStatus, "slate" | "blue" | "green" | "amber" | "red"> = { pending: "slate", scheduled: "blue", completed: "green", rescheduled: "amber", cancelled: "red" };

export default function InterviewsPage() {
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["interviews", status, page], queryFn: async () => (await api.get<Page<InterviewItem>>("/interviews", { params: { status: status || undefined, page, page_size: 15 } })).data });
  return (
    <>
      <PageHeader title="Interviews" description="Interviews for shortlisted candidates. Schedule one from a candidate's result page. Interviewers see the interviews assigned to them." />
      <Card>
        <div className="border-b border-slate-200 p-4">
          <Select aria-label="Filter by status" className="w-full sm:w-52" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="">All statuses</option>{["pending", "scheduled", "rescheduled", "completed", "cancelled"].map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
        </div>
        {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.items.length === 0 ? (
          <EmptyState title="No interviews" description="Shortlist a candidate on the Results page, then schedule their interview." />
        ) : (
          <>
            <TableWrap>
              <thead><tr><th className={th}>Candidate</th><th className={th}>When</th><th className={th}>Type</th><th className={th}>Interviewer</th><th className={th}>Status</th></tr></thead>
              <tbody>
                {data.items.map((i) => (
                  <tr key={i.id} className="hover:bg-slate-50/60">
                    <td className={td}><Link to={`/interviews/${i.id}`} className="font-medium text-slate-900 hover:underline">{i.candidate_name}</Link><span className="block text-xs text-slate-500">{i.opening_title}</span></td>
                    <td className={`${td} text-sm`}>{i.scheduled_start ? formatDateTime(i.scheduled_start) : <span className="text-slate-400">Not set</span>}</td>
                    <td className={`${td} capitalize`}>{i.interview_type} · {i.mode}</td>
                    <td className={td}>{i.interviewer?.full_name ?? <span className="text-slate-400">Unassigned</span>}</td>
                    <td className={td}><Badge tone={INTERVIEW_TONE[i.status]}>{i.status}</Badge></td>
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
