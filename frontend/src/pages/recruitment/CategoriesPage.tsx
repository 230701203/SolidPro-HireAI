import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { api, errorMessage, fieldErrors } from "@/services/api";
import { Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Modal, PageHeader, Spinner, TableWrap, Textarea, TextInput, td, th } from "@/components/ui";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/components/Toast";
import type { Category } from "@/types";

type Editing = { mode: "create" } | { mode: "edit"; category: Category } | null;

function CategoryDialog({ editing, onClose }: { editing: NonNullable<Editing>; onClose: () => void }) {
  const cat = editing.mode === "edit" ? editing.category : null;
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState(cat?.name ?? "");
  const [description, setDescription] = useState(cat?.description ?? "");
  const [isIntern, setIsIntern] = useState(cat?.is_internship ?? false);
  const [error, setError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | undefined>();

  const save = useMutation({
    mutationFn: () =>
      cat
        ? api.patch(`/job-categories/${cat.id}`, { name, description: description || null, is_internship: isIntern })
        : api.post("/job-categories", { name, description: description || null, is_internship: isIntern }),
    onSuccess: () => {
      toast.success(cat ? "Category updated." : "Category added.");
      void qc.invalidateQueries({ queryKey: ["categories"] });
      onClose();
    },
    onError: (e) => {
      setNameError(fieldErrors(e).name);
      setError(errorMessage(e));
    },
  });

  return (
    <Modal
      open
      onClose={onClose}
      title={cat ? "Edit category" : "Add category"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={save.isPending}>Cancel</Button>
          <Button loading={save.isPending} disabled={name.trim().length < 2} onClick={() => { setError(null); setNameError(undefined); save.mutate(); }}>Save</Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && !nameError && <Alert kind="error">{error}</Alert>}
        <Field label="Name" htmlFor="cat-name" error={nameError}><TextInput id="cat-name" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} placeholder="e.g. Python Developer" /></Field>
        <Field label="Description (optional)" htmlFor="cat-desc"><Textarea id="cat-desc" rows={3} value={description} maxLength={1000} onChange={(e) => setDescription(e.target.value)} /></Field>
        <label className="flex items-start gap-2 text-sm text-slate-700">
          <input type="checkbox" className="mt-0.5 size-4 rounded border-slate-300" checked={isIntern} onChange={(e) => setIsIntern(e.target.checked)} />
          <span>Internship category <span className="block text-xs text-slate-500">Openings in this category show the internship fields (college, stipend, duration…).</span></span>
        </label>
      </div>
    </Modal>
  );
}

export default function CategoriesPage() {
  const { hasPermission } = useAuth();
  const canManage = hasPermission("manage_categories");
  const qc = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState<Editing>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["categories", "all"],
    queryFn: async () => (await api.get<Category[]>("/job-categories", { params: { include_inactive: true } })).data,
  });

  const toggle = useMutation({
    mutationFn: (c: Category) => api.patch(`/job-categories/${c.id}`, { is_active: !c.is_active }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["categories"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <PageHeader
        title="Job categories"
        description="Recruitment categories group job openings (they are not account types)."
        actions={canManage && <Button onClick={() => setEditing({ mode: "create" })}><Plus className="size-4" /> Add category</Button>}
      />
      <Card>
        {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.length === 0 ? (
          <EmptyState title="No categories yet" />
        ) : (
          <TableWrap>
            <thead><tr><th className={th}>Name</th><th className={th}>Type</th><th className={th}>Openings</th><th className={th}>Status</th>{canManage && <th className={`${th} text-right`}>Actions</th>}</tr></thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id}>
                  <td className={td}><span className="font-medium text-slate-900">{c.name}</span>{c.description && <span className="block text-xs text-slate-500">{c.description}</span>}</td>
                  <td className={td}>{c.is_internship ? <Badge tone="purple">Internship</Badge> : <Badge>Standard</Badge>}</td>
                  <td className={`${td} tabular-nums`}>{c.openings_count}</td>
                  <td className={td}><Badge tone={c.is_active ? "green" : "slate"}>{c.is_active ? "Active" : "Inactive"}</Badge></td>
                  {canManage && (
                    <td className={`${td} text-right`}>
                      <div className="flex justify-end gap-2">
                        <Button size="sm" variant="secondary" onClick={() => setEditing({ mode: "edit", category: c })}>Edit</Button>
                        <Button size="sm" variant="ghost" loading={toggle.isPending && toggle.variables?.id === c.id} onClick={() => toggle.mutate(c)}>{c.is_active ? "Deactivate" : "Activate"}</Button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </TableWrap>
        )}
      </Card>
      <p className="mt-3 text-xs text-slate-500">A category with openings cannot be removed, only deactivated. Deactivated categories cannot be used for new openings.</p>
      {editing && <CategoryDialog key={editing.mode === "edit" ? editing.category.id : "new"} editing={editing} onClose={() => setEditing(null)} />}
    </>
  );
}
