import { useState } from "react";
import { X } from "lucide-react";
import { inputClass } from "@/components/ui";

/** Type a value and press Enter or comma to add it. Values are de-duplicated case-insensitively. */
export default function TagInput({ id, value, onChange, placeholder, max = 60 }: { id?: string; value: string[]; onChange: (v: string[]) => void; placeholder?: string; max?: number }) {
  const [draft, setDraft] = useState("");

  const add = (raw: string) => {
    const parts = raw.split(",").map((p) => p.trim()).filter(Boolean);
    if (!parts.length) return;
    const next = [...value];
    for (const p of parts) if (next.length < max && !next.some((v) => v.toLowerCase() === p.toLowerCase())) next.push(p.slice(0, 100));
    onChange(next);
    setDraft("");
  };

  return (
    <div className={`${inputClass} flex flex-wrap items-center gap-1.5 !py-1.5 focus-within:border-brand-600 focus-within:ring-2 focus-within:ring-brand-600/20`}>
      {value.map((t) => (
        <span key={t} className="inline-flex items-center gap-1 rounded-md bg-brand-50 px-2 py-1 text-xs font-medium text-brand-800">
          {t}
          <button type="button" aria-label={`Remove ${t}`} onClick={() => onChange(value.filter((v) => v !== t))} className="hover:text-red-600"><X className="size-3" /></button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        placeholder={value.length ? "" : placeholder}
        className="min-w-32 flex-1 border-0 bg-transparent p-1 text-sm outline-none"
        onChange={(e) => (e.target.value.includes(",") ? add(e.target.value) : setDraft(e.target.value))}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); add(draft); }
          if (e.key === "Backspace" && !draft && value.length) onChange(value.slice(0, -1));
        }}
        onBlur={() => add(draft)}
      />
    </div>
  );
}
