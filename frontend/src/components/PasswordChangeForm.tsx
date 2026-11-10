import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Alert, Button, Field, PasswordInput } from "@/components/ui";
import { api, errorMessage, fieldErrors } from "@/services/api";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/components/Toast";
import { passwordSchema } from "@/utils/passwordRules";
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
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) });

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
        <PasswordInput id="current_password" autoComplete="current-password" invalid={!!errors.current_password} {...register("current_password")} />
      </Field>
      <Field label="New password" htmlFor="new_password" error={errors.new_password?.message} hint="10+ characters with upper-case, lower-case and a number.">
        <PasswordInput id="new_password" autoComplete="new-password" invalid={!!errors.new_password} {...register("new_password")} />
      </Field>
      <Field label="Confirm new password" htmlFor="confirm" error={errors.confirm?.message}>
        <PasswordInput id="confirm" autoComplete="new-password" invalid={!!errors.confirm} {...register("confirm")} />
      </Field>
      <Button type="submit" loading={isSubmitting}>Change password</Button>
    </form>
  );
}
