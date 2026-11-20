import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Upload } from "lucide-react";
import { api, errorMessage, fieldErrors } from "@/services/api";
import { Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Modal, PageHeader, Pagination, Select, Spinner, TableWrap, Textarea, TextInput, td, th, useDebounced } from "@/components/ui";
import QuestionEditor, { emptyDraft, validateDraft, type QuestionDraft } from "@/components/QuestionEditor";
import QuestionImportDialog from "@/components/QuestionImportDialog";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/components/Toast";
import type { Bank, BankQuestion, Page } from "@/types";

const TOPICS = [
  { value: "numerical", label: "Numerical ability" }, { value: "logical", label: "Logical reasoning" }, { value: "analytical", label: "Analytical reasoning" },
  { value: "verbal", label: "Verbal ability" }, { value: "data_interpretation", label: "Data interpretation" }, { value: "pattern", label: "Pattern recognition" },
];
const topicLabel = (v: string) => TOPICS.find((t) => t.value === v)?.label ?? v;

function BankDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => api.post("/question-banks", { name: name.trim(), description: description.trim() || null }),
    onSuccess: () => { toast.success("Bank created."); void qc.invalidateQueries({ queryKey: ["banks"] }); onClose(); },
    onError: (e) => setErr(fieldErrors(e).name ?? errorMessage(e)),
  });
  return (
    <Modal open onClose={onClose} title="New question bank" footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={m.isPending} disabled={name.trim().length < 2} onClick={() => { setErr(null); m.mutate(); }}>Create</Button></>}>
      <div className="space-y-3">{err && <Alert kind="error">{err}</Alert>}
        <Field label="Name" htmlFor="bank-name"><TextInput id="bank-name" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Description (optional)" htmlFor="bank-desc"><Textarea id="bank-desc" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></Field></div>
    </Modal>
  );
}

export default function QuestionBankPage() {
  const { hasPermission } = useAuth();
  const canManage = hasPermission("manage_question_bank");
  const qc = useQueryClient();
  const toast = useToast();
  const [bankId, setBankId] = useState<number | null>(null);
  const [topic, setTopic] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<BankQuestion | "new" | null>(null);
  const [newBank, setNewBank] = useState(false);
  const [importing, setImporting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const debounced = useDebounced(search);
  useEffect(() => setPage(1), [topic, difficulty, debounced, bankId]);

  const banks = useQuery({ queryKey: ["banks"], queryFn: async () => (await api.get<Bank[]>("/question-banks")).data });
  const current = bankId ?? banks.data?.[0]?.id ?? null;
  const qs = useQuery({
    queryKey: ["bank-questions", current, topic, difficulty, debounced, page], enabled: current !== null,
    queryFn: async () => (await api.get<Page<BankQuestion>>(`/question-banks/${current}/questions`, { params: { topic: topic || undefined, difficulty: difficulty || undefined, search: debounced || undefined, page, page_size: 15 } })).data,
  });
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["bank-questions"] }); void qc.invalidateQueries({ queryKey: ["banks"] }); };
  const save = useMutation({
    mutationFn: async (d: QuestionDraft) => {
      const body = { topic: d.topic, text: d.text.trim(), options: d.options.map((o) => o.trim()), correct_index: d.correct_index, explanation: d.explanation.trim() || null, difficulty: d.difficulty, marks: d.marks };
      return editing && editing !== "new" ? api.patch(`/question-banks/${current}/questions/${editing.id}`, body) : api.post(`/question-banks/${current}/questions`, body);
    },
    onSuccess: () => { toast.success("Question saved."); setEditing(null); setErr(null); refresh(); },
    onError: (e) => setErr(errorMessage(e)),
  });
  const toggle = useMutation({
    mutationFn: (q: BankQuestion) => api.patch(`/question-banks/${current}/questions/${q.id}`, { is_active: !q.is_active }),
    onSuccess: refresh, onError: (e) => toast.error(errorMessage(e)),
  });
  const bank = banks.data?.find((b) => b.id === current);
  const initial = (): QuestionDraft => editing && editing !== "new"
    ? { ...emptyDraft("aptitude"), text: editing.text, options: editing.options, correct_index: editing.correct_index, explanation: editing.explanation ?? "", difficulty: editing.difficulty, topic: editing.topic, marks: editing.marks }
    : { ...emptyDraft("aptitude"), topic: "numerical" };

  return (
    <>
      <PageHeader title="Aptitude question bank" description="Reusable aptitude questions with verified answer keys. Questions are copied into an assessment, so editing the bank never changes an assessment that already exists."
        actions={canManage && <Button variant="secondary" onClick={() => setNewBank(true)}><Plus className="size-4" /> New bank</Button>} />
      {banks.isLoading ? <Spinner /> : banks.error || !banks.data ? <Card><ErrorState message={errorMessage(banks.error)} /></Card> : (
        <Card>
          <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 p-4">
            <Select aria-label="Question bank" className="w-full sm:w-72" value={current ?? ""} onChange={(e) => setBankId(Number(e.target.value))}>
              {banks.data.map((b) => <option key={b.id} value={b.id}>{b.name} ({b.active_question_count})</option>)}
            </Select>
            <Select aria-label="Filter by topic" className="w-full sm:w-52" value={topic} onChange={(e) => setTopic(e.target.value)}><option value="">All topics</option>{TOPICS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</Select>
            <Select aria-label="Filter by difficulty" className="w-full sm:w-40" value={difficulty} onChange={(e) => setDifficulty(e.target.value)}><option value="">Any difficulty</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></Select>
            <TextInput aria-label="Search questions" placeholder="Search" className="min-w-40 flex-1" value={search} onChange={(e) => setSearch(e.target.value)} />
            {canManage && current !== null && <Button variant="secondary" onClick={() => setImporting(true)}><Upload className="size-4" /> Import from Excel</Button>}
            {canManage && current !== null && <Button onClick={() => { setErr(null); setEditing("new"); }}><Plus className="size-4" /> Add question</Button>}
          </div>
          {bank?.description && <p className="border-b border-slate-100 px-4 py-2 text-xs text-slate-500">{bank.description}</p>}
          {qs.isLoading ? <Spinner /> : qs.error || !qs.data ? <ErrorState message={errorMessage(qs.error)} /> : qs.data.items.length === 0 ? <EmptyState title="No questions match" /> : (
            <>
              <TableWrap>
                <thead><tr><th className={th}>Question</th><th className={th}>Topic</th><th className={th}>Difficulty</th><th className={th}>Status</th>{canManage && <th className={`${th} text-right`}>Actions</th>}</tr></thead>
                <tbody>
                  {qs.data.items.map((q) => (
                    <tr key={q.id}>
                      <td className={td}><span className="text-slate-900">{q.text}</span><span className="block text-xs text-green-700">Answer: {q.options[q.correct_index]}</span></td>
                      <td className={td}>{topicLabel(q.topic)}</td><td className={td}>{q.difficulty}</td>
                      <td className={td}><Badge tone={q.is_active ? "green" : "slate"}>{q.is_active ? "Active" : "Inactive"}</Badge>{q.source === "seed" && <span className="ml-1 text-xs text-slate-500">starter</span>}{q.source === "import" && <span className="ml-1 text-xs text-slate-500">{q.verified_by_name ? "imported" : "imported, unverified"}</span>}</td>
                      {canManage && <td className={`${td} text-right`}><div className="flex justify-end gap-2"><Button size="sm" variant="secondary" onClick={() => { setErr(null); setEditing(q); }}>Edit</Button><Button size="sm" variant="ghost" onClick={() => toggle.mutate(q)}>{q.is_active ? "Deactivate" : "Activate"}</Button></div></td>}
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
              <Pagination page={qs.data.page} pages={qs.data.pages} total={qs.data.total} pageSize={qs.data.page_size} onPage={setPage} />
            </>
          )}
        </Card>
      )}
      <p className="mt-3 text-xs text-slate-500">The starter set is a convenience. Have a person review the answer keys and add role-specific questions before relying on it.</p>
      {editing && <QuestionEditor key={editing === "new" ? "new" : editing.id} title={editing === "new" ? "Add aptitude question" : "Edit aptitude question"} initial={initial()} saving={save.isPending} error={err}
        topicOptions={TOPICS} notice="Assessments that already copied this question are not affected." onSave={(d) => { if (!validateDraft(d)) save.mutate(d); }} onClose={() => setEditing(null)} />}
      {importing && current !== null && bank && <QuestionImportDialog bankId={current} bankName={bank.name} onClose={() => setImporting(false)} />}
      {newBank && <BankDialog onClose={() => setNewBank(false)} />}
    </>
  );
}
