import { Check, X } from "lucide-react";
import { strength, type PasswordCheck } from "@/utils/validation";

/** "12 / 60", turning amber near the limit. */
export function CharCount({ value, max, id }: { value: string; max: number; id?: string }) {
  const n = value.length;
  return <span id={id} className={`text-xs tabular-nums ${n >= max ? "text-red-600" : n >= max * 0.85 ? "text-amber-600" : "text-slate-400"}`} aria-label={`${n} of ${max} characters used`}>{n} / {max}</span>;
}

/** Instant verdict under a field: red problem text, or a green tick once the value passes. */
export function LiveHint({ value, problem, okText }: { value: string; problem: string | null; okText: string }) {
  if (!value) return null;
  return problem ? (
    <p role="status" className="mt-1 flex items-start gap-1 text-xs text-red-600"><X className="mt-0.5 size-3.5 shrink-0" aria-hidden />{problem}</p>
  ) : (
    <p role="status" className="mt-1 flex items-center gap-1 text-xs text-emerald-700"><Check className="size-3.5" aria-hidden />{okText}</p>
  );
}

const BAR = ["bg-slate-200", "bg-red-500", "bg-amber-500", "bg-lime-500", "bg-emerald-600"];
const LABEL = ["", "text-red-600", "text-amber-600", "text-lime-700", "text-emerald-700"];

/** Strength meter, requirement chips (grey until met, then green) and a red message only for rules that are actually broken. */
export function PasswordChecklist({ checks, password }: { checks: PasswordCheck[]; password: string }) {
  const s = strength(checks, password);
  const core = checks.filter((c) => c.core);
  const broken = password ? checks.filter((c) => !c.core && !c.ok) : [];
  return (
    <div className="mt-2 space-y-2.5" data-testid="password-checklist">
      <div className="flex items-center gap-3" aria-live="polite">
        <div className="flex h-1.5 flex-1 gap-1" aria-hidden>
          {[1, 2, 3, 4].map((i) => <span key={i} className={`flex-1 rounded-full transition-colors ${s.score >= i ? BAR[s.score] : "bg-slate-200"}`} />)}
        </div>
        <span className={`min-w-[6.5rem] text-right text-xs font-medium ${LABEL[s.score]}`}>{s.label ? `Strength: ${s.label}` : "Strength"}</span>
      </div>
      <ul className="flex flex-wrap gap-1.5" aria-label="Password requirements">
        {core.map((c) => (
          <li key={c.id} className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs transition-colors ${c.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-slate-200 bg-slate-50 text-slate-500"}`}>
            {c.ok ? <Check className="size-3.5" aria-hidden /> : <span className="size-1.5 rounded-full bg-slate-300" aria-hidden />}
            <span>{c.short}<span className="sr-only">{c.ok ? " (met)" : " (not met)"}</span></span>
          </li>
        ))}
      </ul>
      {broken.length > 0 && (
        <ul className="space-y-1" role="alert">
          {broken.map((c) => <li key={c.id} className="flex items-start gap-1.5 text-xs text-red-600"><X className="mt-0.5 size-3.5 shrink-0" aria-hidden /><span>{c.problem}</span></li>)}
        </ul>
      )}
    </div>
  );
}
