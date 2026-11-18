import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Alert, Button, Field, PasswordInput } from "@/components/ui";
import { api, errorMessage, fieldErrors } from "@/services/api";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/components/Toast";
import { LIMITS, passwordChecks, passwordSchema } from "@/utils/validation";
import { CharCount, PasswordChecklist } from "@/components/LiveChecks";
import type { User } from "@/types";

const schema = z
  .object({ current_password: z.string().min(1, "Enter your current password"), new_password: passwordSchema, confirm: z.string() })
  .refine((d) => d.new_password === d.confirm, { path: ["confirm"], message: "Passwords do not match" });
type Form = z.infer<typeof schema>;

export default function PasswordChangeForm({ onDone }: { onDone?: (u: User) => void }) {
  const { setUser } = useAuth();
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    setError: setFieldError,
    watch,
    formState: { errors, isSubmitting, isSubmitted },
  } = useForm<Form>({ resolver: zodResolver(schema), mode: "onChange" });

  const pwValue = watch("new_password") ?? "";
  const confirmValue = watch("confirm") ?? "";

  const onSubmit = async (v: Form) => {
    setError(null);
    try {
      const { data } = await api.post<User>("/auth/change-password", { current_password: v.current_password, new_password: v.new_password });
      setUser(data);
      reset();
      toast.success("Password changed. Other devices were signed out.");
      onDone?.(data);
    } catch (e) {
      Object.entries(fieldErrors(e)).forEach(([k, m]) => setFieldError(k as keyof Form, { message: m }));
      setError(errorMessage(e));
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      {error && <Alert kind="error">{error}</Alert>}
      <Field label="Current password" htmlFor="current_password" error={errors.current_password?.message}>
        <PasswordInput id="current_password" autoComplete="current-password" maxLength={LIMITS.loginPasswordMax} invalid={!!errors.current_password} {...register("current_password")} />
      </Field>
      <Field label="New password" htmlFor="new_password" error={isSubmitted ? errors.new_password?.message : undefined}>
          <PasswordInput id="new_password" autoComplete="new-password" maxLength={LIMITS.passwordMax} aria-describedby="pw-rules" invalid={!!errors.new_password && pwValue.length > 0} {...register("new_password")} />
          <div id="pw-rules"><PasswordChecklist checks={passwordChecks(pwValue)} password={pwValue} /></div>
          <div className="mt-1 text-right"><CharCount value={pwValue} max={LIMITS.passwordMax} /></div>
        </Field>
      <Field label="Confirm new password" htmlFor="confirm" error={confirmValue ? errors.confirm?.message : undefined}>
          <PasswordInput id="confirm" autoComplete="new-password" maxLength={LIMITS.passwordMax} invalid={!!errors.confirm && confirmValue.length > 0} {...register("confirm")} />
          {confirmValue && confirmValue === pwValue && <p role="status" className="mt-1 text-xs text-emerald-700">Passwords match</p>}
      </Field>
      <Button type="submit" loading={isSubmitting}>Change password</Button>
    </form>
  );
}
