import { z } from "zod";
import { mobileProblem } from "./mobile";

/**
 * Input rules shared by the sign-in, register, reset and change-password forms.
 * They mirror backend/app/core/security.py. The server stays the source of truth, so a rule changed here
 * must be changed there too. Sign-in deliberately checks only shape and length so an existing account is never
 * locked out by a stricter rule.
 */
export const LIMITS = { emailMax: 254, emailLocalMax: 64, nameMin: 2, nameMax: 60, passwordMin: 10, passwordMax: 64, loginPasswordMax: 128 } as const;
export const SPECIAL_CHARS = "!@#$%^&*()_+-=[]{};':\",.<>/?\\|`~";
const COMMON = ["password", "qwerty", "123456", "letmein", "iloveyou", "welcome1", "admin123"];

/** Returns a human message when the email is not acceptable, else null. */
export function emailProblem(raw: string): string | null {
  const e = raw.trim();
  if (!e) return "Enter your email";
  if (e.length > LIMITS.emailMax) return `Email must be at most ${LIMITS.emailMax} characters`;
  if (/\s/.test(e) || (e.match(/@/g) ?? []).length !== 1) return "Enter a valid email address such as name@company.com";
  const [local, domain] = e.split("@");
  if (!local) return "Add the part before @ (for example name@company.com)";
  if (local.length > LIMITS.emailLocalMax) return `The part before @ must be at most ${LIMITS.emailLocalMax} characters`;
  if (local.includes("..") || !/^[A-Za-z0-9](?:[A-Za-z0-9._%+-]*[A-Za-z0-9])?$/.test(local))
    return "Before @ use only letters, numbers and . _ % + - (no leading, trailing or double dots)";
  if (!/[A-Za-z]/.test(local)) return "The part before @ must contain at least one letter";
  const labels = domain.split(".");
  if (labels.length < 2 || labels.some((l) => !l || l.length > 63 || !/^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$/.test(l))) return "The domain after @ must look like company.com";
  if (!/^[A-Za-z]{2,24}$/.test(labels[labels.length - 1])) return "The domain must end with an extension such as .com or .in";
  return null;
}

export function nameProblem(raw: string): string | null {
  const n = raw.trim().replace(/\s+/g, " ");
  if (!n) return "Enter your full name";
  if (n.length < LIMITS.nameMin) return `Name must be at least ${LIMITS.nameMin} characters`;
  if (n.length > LIMITS.nameMax) return `Name must be at most ${LIMITS.nameMax} characters`;
  if (!/^[\p{L}][\p{L}\p{M} .'-]*$/u.test(n) || /[.'-]{2,}/.test(n)) return "Use letters, spaces and . ' - only, starting with a letter";
  return null;
}

export type PasswordCheck = {
  id: string;
  /** Full sentence, used in error messages. */
  label: string;
  /** Short chip text for the checklist. */
  short: string;
  ok: boolean;
  /** Core rules are always shown as chips; the others only appear, as a message, when broken. */
  core: boolean;
  /** Message shown when a non-core rule is broken. */
  problem?: string;
};

/** Every rule, evaluated live. `email` (register only) enables the "not your email" rule. */
export function passwordChecks(pw: string, email?: string): PasswordCheck[] {
  const low = pw.toLowerCase();
  const local = (email ?? "").split("@")[0].toLowerCase();
  const checks: PasswordCheck[] = [
    { id: "length", label: `${LIMITS.passwordMin} to ${LIMITS.passwordMax} characters`, short: `${LIMITS.passwordMin}+ characters`, core: true, ok: pw.length >= LIMITS.passwordMin && pw.length <= LIMITS.passwordMax },
    { id: "lower", label: "A lowercase letter (a-z)", short: "Lowercase a-z", core: true, ok: /[a-z]/.test(pw) },
    { id: "upper", label: "An uppercase letter (A-Z)", short: "Uppercase A-Z", core: true, ok: /[A-Z]/.test(pw) },
    { id: "digit", label: "A number (0-9)", short: "Number 0-9", core: true, ok: /\d/.test(pw) },
    { id: "symbol", label: "A symbol such as ! @ # $ %", short: "Symbol ! @ #", core: true, ok: [...pw].some((c) => SPECIAL_CHARS.includes(c)) },
    { id: "chars", label: "English letters, numbers and symbols only, no spaces", short: "Allowed characters", core: false, ok: pw.length > 0 && /^[\x21-\x7e]+$/.test(pw), problem: "Use English letters, numbers and symbols only, with no spaces" },
    { id: "common", label: "No common words such as “password” or “123456”", short: "Not a common word", core: false, ok: pw.length > 0 && !COMMON.some((w) => low.includes(w)), problem: "Avoid common words such as “password” or “123456”" },
  ];
  if (email !== undefined) checks.push({ id: "email", label: "Does not contain your email name", short: "Not your email", core: false, ok: pw.length > 0 && !(local.length >= 6 && low.includes(local)) && low !== (email ?? "").toLowerCase(), problem: "Do not include your email name in the password" });
  return checks;
}

/** Four-step strength: 0 nothing typed, 1 weak, 2 fair, 3 good, 4 strong. Breaking a hidden rule caps it at weak. */
export function strength(checks: PasswordCheck[], pw: string): { score: 0 | 1 | 2 | 3 | 4; label: string } {
  if (!pw) return { score: 0, label: "" };
  if (checks.some((c) => !c.core && !c.ok)) return { score: 1, label: "Weak" };
  const met = checks.filter((c) => c.core && c.ok).length;
  if (met <= 2) return { score: 1, label: "Weak" };
  if (met < 5) return { score: 2, label: "Fair" };
  return pw.length >= 14 ? { score: 4, label: "Strong" } : { score: 3, label: "Good" };
}

export const emailSchema = z.string().superRefine((v, ctx) => { const p = emailProblem(v); if (p) ctx.addIssue({ code: "custom", message: p }); });
export const nameSchema = z.string().superRefine((v, ctx) => { const p = nameProblem(v); if (p) ctx.addIssue({ code: "custom", message: p }); });
export const makePasswordSchema = (getEmail?: () => string | undefined) =>
  z.string().superRefine((v, ctx) => {
    const bad = passwordChecks(v, getEmail?.()).find((c) => !c.ok);
    if (bad) ctx.addIssue({ code: "custom", message: `Password needs: ${bad.label.toLowerCase()}` });
  });
export const passwordSchema = makePasswordSchema();
export const mobileSchema = z.string().superRefine((v, ctx) => { const p = mobileProblem(v); if (p) ctx.addIssue({ code: "custom", message: p }); });
