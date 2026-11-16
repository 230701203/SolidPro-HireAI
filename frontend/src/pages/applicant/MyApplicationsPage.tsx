import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Card, EmptyState, ErrorState, PageHeader, Pagination, Spinner, TableWrap, td, th } from "@/components/ui";
import { ApplicationStatusBadge } from "@/components/badges";
import { formatDate } from "@/utils/format";
import type { ApplicationListItem, Page } from "@/types";

export default function MyApplicationsPage() {
  const [page, setPage] = useState(1);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["my-applications", page],
    queryFn: async () => (await api.get<Page<ApplicationListItem>>("/applications", { params: { page, page_size: 15 } })).data,
  });
  return (
    <>
      <PageHeader title="My applications" description="Track where each application stands." />
      <Card>
        {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.items.length === 0 ? (
          <EmptyState title="You haven't applied yet" description="Browse open positions and apply." action={<Link to="/jobs" className="text-sm font-medium text-brand-700 hover:underline">Browse jobs</Link>} />
        ) : (
          <>
            <TableWrap>
              <thead><tr><th className={th}>Opening</th><th className={th}>Status</th><th className={th}>Applied</th><th className={th}>Updated</th></tr></thead>
              <tbody>
                {data.items.map((a) => (
                  <tr key={a.id} className="hover:bg-slate-50/60">
                    <td className={td}><Link to={`/my-applications/${a.id}`} className="font-medium text-slate-900 hover:underline">{a.opening_title}</Link><span className="block text-xs text-slate-500">{a.category_name}</span></td>
                    <td className={td}><ApplicationStatusBadge status={a.status} /></td><td className={td}>{formatDate(a.submitted_at)}</td><td className={td}>{formatDate(a.updated_at)}</td>
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
