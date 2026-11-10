import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Alert, Badge, Button, Card, EmptyState, ErrorState, Field, PageHeader, Spinner, TextInput } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { formatDate } from "@/utils/format";
import type { EmailDomain } from "@/types";

export default function SettingsPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const [domain, setDomain] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, error: loadError, refetch } = useQuery({
    queryKey: ["email-domains"],
    queryFn: async () => (await api.get<EmailDomain[]>("/settings/email-domains")).data,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["email-domains"] });

  const add = useMutation({
    mutationFn: () => api.post<EmailDomain>("/settings/email-domains", { domain }),
    onSuccess: (r) => { toast.success(`${r.data.domain} added.`); setDomain(""); setError(null); void refresh(); },
    onError: (e) => setError(errorMessage(e)),
  });
  const toggle = useMutation({
    mutationFn: (d: EmailDomain) => api.patch(`/settings/email-domains/${d.id}`, { is_active: !d.is_active }),
    onSuccess: () => void refresh(),
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <PageHeader title="System settings" description="Control which email domains count as SolidPro company addresses." />
      <Card className="max-w-3xl">
        <div className="border-b border-slate-200 p-5">
          <h2 className="font-semibold text-slate-900">Verified company email domains</h2>
          <p className="mt-1 text-sm text-slate-500">New registrations from these domains enter the employee approval queue. A company address never grants access by itself; an administrator must still approve it.</p>
        </div>
        <form className="flex flex-wrap items-end gap-3 border-b border-slate-200 p-5" onSubmit={(e) => { e.preventDefault(); setError(null); add.mutate(); }}>
          <div className="min-w-56 flex-1"><Field label="Add domain" htmlFor="domain"><TextInput id="domain" placeholder="company.com" value={domain} onChange={(e) => setDomain(e.target.value)} /></Field></div>
          <Button type="submit" loading={add.isPending} disabled={domain.trim().length < 3}>Add domain</Button>
        </form>
        {error && <div className="px-5 pt-4"><Alert kind="error">{error}</Alert></div>}
        {isLoading ? <Spinner /> : loadError || !data ? <ErrorState message={errorMessage(loadError)} onRetry={() => void refetch()} /> : data.length === 0 ? (
          <EmptyState title="No domains configured" description="Without a company domain, every registration becomes an applicant account." />
        ) : (
          <ul className="divide-y divide-slate-100">
            {data.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-3 px-5 py-3">
                <div><p className="font-medium text-slate-900">@{d.domain}</p><p className="text-xs text-slate-500">Added {formatDate(d.created_at)}</p></div>
                <div className="flex items-center gap-3">
                  <Badge tone={d.is_active ? "green" : "slate"}>{d.is_active ? "Active" : "Inactive"}</Badge>
                  <Button size="sm" variant="secondary" loading={toggle.isPending && toggle.variables?.id === d.id} onClick={() => toggle.mutate(d)}>{d.is_active ? "Deactivate" : "Activate"}</Button>
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="border-t border-slate-200 px-5 py-3 text-xs text-slate-500">Deactivating a domain only affects new sign-ups; existing employees keep their accounts.</p>
      </Card>
    </>
  );
}
