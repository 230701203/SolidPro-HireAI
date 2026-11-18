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

export function PasswordChecklist({ checks, password }: { checks: PasswordCheck[]; password: string }) {
  const s = strength(checks, password);
  const colors = ["bg-slate-200", "bg-red-500", "bg-amber-500", "bg-emerald-600"];
  return (
    <div className="mt-2 space-y-2" data-testid="password-checklist">
      <div className="flex items-center gap-2" aria-live="polite">
        <div className="flex h-1.5 flex-1 gap-1" aria-hidden>
          {[1, 2, 3].map((i) => <span key={i} className={`flex-1 rounded ${s.score >= i ? colors[s.score] : "bg-slate-200"}`} />)}
        </div>
        <span className="w-20 text-right text-xs text-slate-600">{s.label ? `Strength: ${s.label}` : ""}</span>
      </div>
      <ul className="grid gap-x-4 gap-y-1 sm:grid-cols-2">
        {checks.map((c) => (
          <li key={c.id} className={`flex items-start gap-1.5 text-xs ${c.ok ? "text-emerald-700" : password ? "text-red-600" : "text-slate-500"}`}>
            {c.ok ? <Check className="mt-0.5 size-3.5 shrink-0" aria-hidden /> : <X className="mt-0.5 size-3.5 shrink-0" aria-hidden />}
            <span>{c.label}<span className="sr-only">{c.ok ? " (met)" : " (not met)"}</span></span>
          </li>
        ))}
      </ul>
    </div>
  );
}
