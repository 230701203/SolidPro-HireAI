/** Mobile number rules. Mirror backend/app/core/security.py `validate_mobile`; change both together. */
export const COUNTRY_CODES = [
  { code: "+91", label: "India (+91)" }, { code: "+1", label: "US / Canada (+1)" }, { code: "+44", label: "United Kingdom (+44)" },
  { code: "+971", label: "UAE (+971)" }, { code: "+966", label: "Saudi Arabia (+966)" }, { code: "+974", label: "Qatar (+974)" },
  { code: "+65", label: "Singapore (+65)" }, { code: "+61", label: "Australia (+61)" }, { code: "+60", label: "Malaysia (+60)" }, { code: "+49", label: "Germany (+49)" },
] as const;

/** Splits a stored number such as "+91 9876543210" into a country code and the rest. Unknown codes come back as "other". */
export function splitMobile(value: string | null | undefined): { code: string; other: boolean; number: string } {
  const v = (value ?? "").trim();
  if (!v) return { code: "+91", other: false, number: "" };
  if (!v.startsWith("+") && /^\d{10}$/.test(v.replace(/[ -]/g, ""))) return { code: "+91", other: false, number: v.replace(/\D/g, "") };
  const m = /^(\+\d{1,4})[ -]?(.*)$/.exec(v);
  if (!m) return { code: "+91", other: false, number: v.replace(/\D/g, "") };
  const known = [...COUNTRY_CODES].sort((a, b) => b.code.length - a.code.length).find((c) => v.replace(/[ -]/g, "").startsWith(c.code));
  if (known) return { code: known.code, other: false, number: v.replace(/[ -]/g, "").slice(known.code.length) };
  return { code: m[1], other: true, number: m[2].replace(/\D/g, "") };
}

export const joinMobile = (code: string, number: string) => (number ? `${code} ${number}` : "");

/** Returns a human message when the number is not acceptable, else null. An empty value is handled by the caller. */
export function mobileProblem(value: string): string | null {
  const raw = value.trim().replace(/[ -]+/g, " ");
  if (!raw) return null;
  if (!/^\+?[0-9][0-9 ]*$/.test(raw)) return "Use digits only";
  const digits = raw.replace(/\D/g, "");
  let national: string;
  if (!raw.startsWith("+")) {
    if (digits.length !== 10) return "Include the country code, for example +91";
    national = digits;
    return indian(national);
  }
  if (digits.startsWith("91")) return indian(digits.slice(2));
  if (digits.startsWith("0") || digits.length < 8 || digits.length > 15) return "Enter 8 to 15 digits including the country code";
  national = digits.slice(-8);
  return new Set(national).size === 1 ? "Enter a real mobile number" : null;
}

function indian(national: string): string | null {
  if (national.length !== 10) return `An Indian mobile number has exactly 10 digits (you entered ${national.length})`;
  if (!/^[6-9]/.test(national)) return "An Indian mobile number starts with 6, 7, 8 or 9";
  return new Set(national).size === 1 ? "Enter a real mobile number" : null;
}
