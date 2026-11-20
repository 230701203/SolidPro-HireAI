import { useState } from "react";
import { Select, TextInput } from "@/components/ui";

const OTHER = "__other__";

/**
 * A dropdown of preset answers plus "Other", which reveals a text box. The value is always the plain text
 * (a preset, or whatever was typed), so it saves exactly like a normal text field. Saved values that are not in
 * the list open as "Other" with the text filled in.
 */
export default function SelectOther({ id, value, onChange, options, placeholder = "Select", otherLabel = "Other (type your own)", otherPlaceholder = "Type here", invalid, maxLength = 150 }: {
  id: string; value: string; onChange: (v: string) => void; options: readonly string[]; placeholder?: string; otherLabel?: string; otherPlaceholder?: string; invalid?: boolean; maxLength?: number;
}) {
  const known = options.includes(value);
  const [otherChosen, setOtherChosen] = useState(false);
  const other = otherChosen || (value !== "" && !known);
  return (
    <div className="space-y-2">
      <Select id={id} aria-invalid={invalid || undefined} value={other ? OTHER : value} onChange={(e) => {
        if (e.target.value === OTHER) { setOtherChosen(true); onChange(""); } else { setOtherChosen(false); onChange(e.target.value); }
      }}>
        <option value="">{placeholder}</option>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
        <option value={OTHER}>{otherLabel}</option>
      </Select>
      {other && <TextInput id={`${id}-other`} aria-label={`${otherLabel.replace(/ \(.*\)/, "")} value`} placeholder={otherPlaceholder} maxLength={maxLength} invalid={invalid} value={value} onChange={(e) => onChange(e.target.value)} />}
    </div>
  );
}
