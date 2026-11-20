import { useState } from "react";
import { Select, TextInput } from "@/components/ui";
import { COUNTRY_CODES, joinMobile, mobileProblem, splitMobile } from "@/utils/mobile";

const OTHER = "other";

/** Country-code dropdown plus a digits-only number box. Emits one string such as "+91 9876543210" (empty when no number). */
export default function MobileInput({ id, value, onChange, invalid }: { id: string; value: string; onChange: (v: string) => void; invalid?: boolean }) {
  const parsed = splitMobile(value);
  const [forceOther, setForceOther] = useState(false);
  const other = forceOther || parsed.other;
  const [code, setCode] = useState(parsed.code);
  const [number, setNumber] = useState(parsed.number);
  const emit = (c: string, n: string) => onChange(joinMobile(c, n));
  const india = code === "+91" && !other;
  const live = !invalid && number ? mobileProblem(joinMobile(code, number)) : null;
  return (
    <div>
    <div className="flex gap-2">
      <div className="w-40 shrink-0 space-y-2">
        <Select aria-label="Country code" value={other ? OTHER : code} onChange={(e) => {
          if (e.target.value === OTHER) { setForceOther(true); setCode("+"); emit("+", number); } else { setForceOther(false); setCode(e.target.value); emit(e.target.value, number); }
        }}>
          {COUNTRY_CODES.map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}
          <option value={OTHER}>Other code…</option>
        </Select>
        {other && <TextInput aria-label="Country code number" inputMode="numeric" maxLength={5} placeholder="+000" value={code} invalid={invalid} onChange={(e) => {
          const c = "+" + e.target.value.replace(/\D/g, "").slice(0, 4); setCode(c); emit(c, number);
        }} />}
      </div>
      <TextInput id={id} type="tel" inputMode="numeric" autoComplete="tel-national" placeholder={india ? "98765 43210" : "Phone number"} maxLength={india ? 10 : 15}
        invalid={invalid} value={number} onChange={(e) => { const n = e.target.value.replace(/\D/g, "").slice(0, india ? 10 : 15); setNumber(n); emit(code, n); }} />
    </div>
    {live && <p className="mt-1 text-xs text-red-600" role="status">{live}</p>}
    </div>
  );
}
