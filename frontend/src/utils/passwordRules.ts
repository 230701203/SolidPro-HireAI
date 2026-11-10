import { z } from "zod";

/** Mirrors the server rules (backend/app/core/security.py). The server remains the source of truth. */
export const passwordSchema = z
  .string()
  .min(10, "At least 10 characters")
  .max(128, "At most 128 characters")
  .regex(/[a-z]/, "Include a lowercase letter")
  .regex(/[A-Z]/, "Include an uppercase letter")
  .regex(/\d/, "Include a digit");

export const mobileSchema = z.string().regex(/^\+?[0-9][0-9 -]{7,17}$/, "Enter a valid mobile number");
