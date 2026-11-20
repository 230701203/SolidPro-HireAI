import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, FileSpreadsheet } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import { Alert, Button, Modal } from "@/components/ui";
import { useToast } from "@/components/Toast";
import type { ImportResult } from "@/types";

const MAX_MB = 5;

/** Upload an .xlsx file of aptitude questions. The file is checked first (nothing is saved); the person then confirms the import. */
export default function QuestionImportDialog({ bankId, bankName, onClose }: { bankId: number; bankName: string; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const run = useMutation({
    mutationFn: async (dryRun: boolean) => {
      const fd = new FormData();
      fd.append("file", file as File);
      return (await api.post<ImportResult>(`/question-banks/${bankId}/import`, fd, { params: { dry_run: dryRun } })).data;
    },
    onSuccess: (r) => {
      setResult(r);
      if (!r.dry_run) {
        toast.success(`${r.imported} question${r.imported === 1 ? "" : "s"} imported.`);
        void qc.invalidateQueries({ queryKey: ["bank-questions"] });
        void qc.invalidateQueries({ queryKey: ["banks"] });
      }
    },
    onError: (e) => setErr(errorMessage(e)),
  });

  const template = async () => {
    try {
      const res = await api.get("/question-banks/import-template", { responseType: "blob" });
      const url = URL.createObjectURL(res.data as Blob);
      const a = document.createElement("a");
      a.href = url; a.download = "question-import-template.xlsx"; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { setErr(errorMessage(e)); }
  };

  const pick = (f?: File) => {
    setErr(null); setResult(null); setFile(null);
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".xlsx")) return setErr("Upload an Excel .xlsx file. Use the template for the right columns.");
    if (f.size > MAX_MB * 1024 * 1024) return setErr(`The file is larger than ${MAX_MB} MB.`);
    setFile(f);
  };

  const done = result && !result.dry_run;
  const canImport = result?.dry_run && result.valid > 0;

  return (
    <Modal open onClose={onClose} title="Import questions from Excel"
      footer={<>
        <Button variant="secondary" onClick={onClose}>{done ? "Close" : "Cancel"}</Button>
        {!done && !canImport && <Button loading={run.isPending} disabled={!file} onClick={() => { setErr(null); run.mutate(true); }}>Check file</Button>}
        {canImport && <Button loading={run.isPending} onClick={() => { setErr(null); run.mutate(false); }}>Import {result.valid} question{result.valid === 1 ? "" : "s"}</Button>}
      </>}>
      <div className="space-y-4 text-sm">
        <p className="text-slate-600">Questions are added to <strong>{bankName}</strong>. Fill in the template (one question per row, 2 to 6 options, correct answer as a letter), then upload it. Nothing is saved until you confirm.</p>
        <Button variant="secondary" size="sm" onClick={() => void template()}><Download className="size-4" /> Download template</Button>
        <div>
          <input ref={input} type="file" aria-label="Excel file" accept=".xlsx" className="hidden" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
          <Button variant="secondary" onClick={() => input.current?.click()}><FileSpreadsheet className="size-4" /> {file ? "Choose a different file" : "Choose Excel file"}</Button>
          {file && <span className="ml-3 text-slate-700">{file.name}</span>}
        </div>
        {err && <Alert kind="error">{err}</Alert>}
        {result && (
          <div className="space-y-2" aria-live="polite">
            <Alert kind={result.failed > 0 ? "warning" : "success"}>
              {done
                ? `Imported ${result.imported} of ${result.total_rows} rows.`
                : `${result.total_rows} rows read: ${result.valid} ready to import, ${result.duplicates} already in the bank, ${result.failed} with problems.`}
              {result.failed > 0 && " Fix the rows below in your file and upload it again; rows already imported are skipped as duplicates."}
            </Alert>
            {result.issues.length > 0 && (
              <ul className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-3 text-xs">
                {result.issues.map((i) => <li key={i.row}><span className="font-medium">Row {i.row}:</span> <span className={i.skipped ? "text-slate-500" : "text-red-700"}>{i.message}</span></li>)}
              </ul>
            )}
            {done && <p className="text-xs text-slate-500">Imported questions are marked unverified. Check each answer key and use Edit to correct anything.</p>}
          </div>
        )}
      </div>
    </Modal>
  );
}
