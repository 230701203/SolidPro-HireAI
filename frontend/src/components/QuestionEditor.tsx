import { useState } from "react";
import { Plus, X } from "lucide-react";
import { Alert, Button, Field, Modal, Select, Textarea, TextInput } from "@/components/ui";
import type { AQuestion, Difficulty, SectionKind } from "@/types";

export interface QuestionDraft {
  section: SectionKind; text: string; options: string[]; correct_index: number; explanation: string;
  difficulty: Difficulty; topic: string; skill: string; marks: number;
}

export function draftFrom(q: AQuestion): QuestionDraft {
  return {
    section: q.section, text: q.text, options: q.options ?? ["", "", "", ""], correct_index: q.correct_index ?? 0, explanation: q.explanation ?? "",
    difficulty: q.difficulty, topic: q.topic ?? "", skill: q.skill ?? "", marks: q.marks,
  };
}

export const emptyDraft = (section: SectionKind): QuestionDraft => ({
  section, text: "", options: section === "repeat_sentence" ? [] : ["", "", "", ""], correct_index: 0, explanation: "",
  difficulty: "medium", topic: "", skill: "", marks: section === "repeat_sentence" ? 2 : 1,
});

/** Request body shared by create and update. Repeat the Sentence items carry no options. */
export function toBody(d: QuestionDraft, creating: boolean) {
  const rs = d.section === "repeat_sentence";
  return {
    ...(creating ? { section: d.section } : {}), text: d.text.trim(), ...(rs ? {} : { options: d.options.map((o) => o.trim()), correct_index: d.correct_index }),
    explanation: d.explanation.trim() || null, difficulty: d.difficulty, topic: d.topic.trim() || null, skill: d.skill.trim() || null, marks: d.marks,
  };
}

export function validateDraft(d: QuestionDraft): string | null {
  if (d.section === "repeat_sentence") {
    const n = d.text.trim().split(/\s+/).filter(Boolean).length;
    return n >= 5 && n <= 30 ? null : "The sentence should be 5 to 30 words.";
  }
  if (d.text.trim().length < 5) return "Write the question.";
  const opts = d.options.map((o) => o.trim());
  if (opts.some((o) => !o)) return "Fill in every answer option (or remove the empty ones).";
  if (new Set(opts.map((o) => o.toLowerCase())).size !== opts.length) return "Answer options must be different from each other.";
  if (d.correct_index < 0 || d.correct_index >= opts.length) return "Mark one option as correct.";
  return null;
}

export default function QuestionEditor({ title, initial, saving, error, onSave, onClose, topicOptions, notice = "Saving marks this question as needing approval again." }: {
  title: string; initial: QuestionDraft; saving: boolean; error: string | null; onSave: (d: QuestionDraft) => void; onClose: () => void;
  /** When given, the topic is chosen from this list (used by the aptitude bank). */
  topicOptions?: { value: string; label: string }[]; notice?: string | null;
}) {
  const [d, setD] = useState(initial);
  const set = <K extends keyof QuestionDraft>(k: K, v: QuestionDraft[K]) => setD((p) => ({ ...p, [k]: v }));
  const rs = d.section === "repeat_sentence";
  const problem = validateDraft(d);
  const setOpt = (i: number, v: string) => set("options", d.options.map((o, j) => (j === i ? v : o)));
  const removeOpt = (i: number) => {
    set("options", d.options.filter((_, j) => j !== i));
    if (d.correct_index === i) set("correct_index", 0);
    else if (d.correct_index > i) set("correct_index", d.correct_index - 1);
  };
  return (
    <Modal open wide onClose={onClose} title={title}
      footer={<><Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button><Button loading={saving} disabled={!!problem} onClick={() => onSave(d)}>Save</Button></>}>
      <div className="space-y-4">
        {error && <Alert kind="error">{error}</Alert>}
        {notice && <Alert kind="info">{notice}</Alert>}
        <Field label={rs ? "Sentence the applicant will hear and repeat" : "Question"} htmlFor="q-text"><Textarea id="q-text" rows={rs ? 2 : 3} maxLength={2000} value={d.text} onChange={(e) => set("text", e.target.value)} /></Field>
        {!rs && (
          <fieldset className="space-y-2">
            <legend className="mb-1 text-sm font-medium text-slate-700">Answer options (select the correct one)</legend>
            {d.options.map((o, i) => (
              <div key={i} className="flex items-center gap-2">
                <input type="radio" name="correct" aria-label={`Option ${i + 1} is correct`} className="size-4" checked={d.correct_index === i} onChange={() => set("correct_index", i)} />
                <TextInput aria-label={`Option ${i + 1}`} value={o} maxLength={300} onChange={(e) => setOpt(i, e.target.value)} />
                {d.options.length > 2 && <button type="button" aria-label={`Remove option ${i + 1}`} className="rounded p-1 text-slate-400 hover:bg-slate-100" onClick={() => removeOpt(i)}><X className="size-4" /></button>}
              </div>
            ))}
            {d.options.length < 6 && <Button type="button" size="sm" variant="ghost" onClick={() => set("options", [...d.options, ""])}><Plus className="size-4" /> Add option</Button>}
          </fieldset>
        )}
        {!rs && <Field label="Explanation" htmlFor="q-expl"><Textarea id="q-expl" rows={2} maxLength={2000} value={d.explanation} onChange={(e) => set("explanation", e.target.value)} /></Field>}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Difficulty" htmlFor="q-diff"><Select id="q-diff" value={d.difficulty} onChange={(e) => set("difficulty", e.target.value as Difficulty)}><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></Select></Field>
          <Field label="Marks" htmlFor="q-marks"><TextInput id="q-marks" type="number" min={1} max={10} value={d.marks} onChange={(e) => set("marks", Math.max(1, Math.min(10, Number(e.target.value) || 1)))} /></Field>
          {!rs && (topicOptions
            ? <Field label="Topic" htmlFor="q-topic"><Select id="q-topic" value={d.topic} onChange={(e) => set("topic", e.target.value)}>{topicOptions.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</Select></Field>
            : <Field label="Topic" htmlFor="q-topic"><TextInput id="q-topic" maxLength={100} value={d.topic} onChange={(e) => set("topic", e.target.value)} /></Field>)}
        </div>
        {!rs && d.section === "mcq" && <Field label="Related job skill" htmlFor="q-skill"><TextInput id="q-skill" maxLength={100} value={d.skill} onChange={(e) => set("skill", e.target.value)} /></Field>}
        {problem && <p role="alert" className="text-xs text-amber-700">{problem}</p>}
      </div>
    </Modal>
  );
}
