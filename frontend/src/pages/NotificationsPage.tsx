import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import { Button, Card, EmptyState, ErrorState, PageHeader, Pagination, Spinner } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { timeAgo } from "@/utils/format";
import type { AppNotification, Page } from "@/types";

export default function NotificationsPage() {
  const [page, setPage] = useState(1);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["notifications", "list", page, unreadOnly],
    queryFn: async () => (await api.get<Page<AppNotification>>("/notifications", { params: { page, page_size: 15, unread_only: unreadOnly } })).data,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["notifications"] });
  const markRead = useMutation({
    mutationFn: (id: number) => api.post(`/notifications/${id}/read`),
    onSuccess: invalidate,
    onError: (e) => toast.error(errorMessage(e)),
  });
  const markAll = useMutation({
    mutationFn: () => api.post("/notifications/read-all"),
    onSuccess: () => { toast.success("All notifications marked as read."); void invalidate(); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const open = (n: AppNotification) => {
    if (!n.is_read) markRead.mutate(n.id);
    if (n.link) navigate(n.link);
  };

  return (
    <>
      <PageHeader
        title="Notifications"
        actions={
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input type="checkbox" className="size-4 rounded border-slate-300" checked={unreadOnly} onChange={(e) => { setUnreadOnly(e.target.checked); setPage(1); }} />
              Unread only
            </label>
            <Button variant="secondary" size="sm" onClick={() => markAll.mutate()} loading={markAll.isPending}><CheckCheck className="size-4" /> Mark all read</Button>
          </div>
        }
      />
      <Card>
        {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.items.length === 0 ? (
          <EmptyState title={unreadOnly ? "No unread notifications" : "No notifications yet"} description="Updates about your account and recruitment activity will appear here." />
        ) : (
          <>
            <ul className="divide-y divide-slate-100">
              {data.items.map((n) => (
                <li key={n.id}>
                  <button onClick={() => open(n)} className={`flex w-full items-start gap-3 px-5 py-4 text-left hover:bg-slate-50 ${n.is_read ? "" : "bg-brand-50/50"}`}>
                    <span className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full ${n.is_read ? "bg-slate-100 text-slate-400" : "bg-brand-100 text-brand-700"}`}><Bell className="size-4" /></span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <span className="text-sm font-medium text-slate-900">{n.title}</span>
                        {!n.is_read && <span className="size-2 rounded-full bg-brand-600" aria-label="Unread" />}
                      </span>
                      <span className="mt-0.5 block text-sm text-slate-600">{n.message}</span>
                    </span>
                    <span className="shrink-0 text-xs text-slate-500">{timeAgo(n.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
            <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={data.page_size} onPage={setPage} />
          </>
        )}
      </Card>
    </>
  );
}
