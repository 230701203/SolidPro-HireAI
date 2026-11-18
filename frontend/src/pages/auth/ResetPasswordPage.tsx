import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import AuthLayout from "@/layouts/AuthLayout";
import { Alert, Button, Field, PasswordInput } from "@/components/ui";
import { api, errorMessage, fieldErrors } from "@/services/api";
import { LIMITS, passwordChecks, passwordSchema } from "@/utils/validation";
import { CharCount, PasswordChecklist } from "@/components/LiveChecks";
import { useToast } from "@/components/Toast";

const schema = z
  .object({ new_password: passwordSchema, confirm: z.string() })
  .refine((d) => d.new_password === d.confirm, { path: ["confirm"], message: "Passwords do not match" });
type Form = z.infer<typeof schema>;

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const navigate = useNavigate();
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError: setFieldError,
    watch,
    formState: { errors, isSubmitting, isSubmitted },
  } = useForm<Form>({ resolver: zodResolver(schema), mode: "onChange" });

  if (!token) {
    return (
      <AuthLayout title="Reset password" footer={<Link to="/forgot-password" className="font-medium text-brand-700 hover:underline">Request a new link</Link>}>
        <Alert kind="error">This reset link is incomplete.</Alert>
      </AuthLayout>
    );
  }

  const pwValue = watch("new_password") ?? "";
  const confirmValue = watch("confirm") ?? "";

  const onSubmit = async (v: Form) => {
    setError(null);
    try {
      await api.post("/auth/reset-password", { token, new_password: v.new_password });
      toast.success("Password updated. Please sign in.");
      navigate("/login", { replace: true });
    } catch (e) {
      Object.entries(fieldErrors(e)).forEach(([k, m]) => setFieldError(k as keyof Form, { message: m }));
      setError(errorMessage(e));
    }
  };

  return (
    <AuthLayout title="Choose a new password" footer={<Link to="/login" className="font-medium text-brand-700 hover:underline">Back to sign in</Link>}>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {error && <Alert kind="error">{error}</Alert>}
        <Field label="New password" htmlFor="new_password" error={isSubmitted ? errors.new_password?.message : undefined}>
          <PasswordInput id="new_password" autoComplete="new-password" maxLength={LIMITS.passwordMax} aria-describedby="pw-rules" invalid={!!errors.new_password && pwValue.length > 0} {...register("new_password")} />
          <div id="pw-rules"><PasswordChecklist checks={passwordChecks(pwValue)} password={pwValue} /></div>
          <div className="mt-1 text-right"><CharCount value={pwValue} max={LIMITS.passwordMax} /></div>
        </Field>
        <Field label="Confirm new password" htmlFor="confirm" error={confirmValue ? errors.confirm?.message : undefined}>
          <PasswordInput id="confirm" autoComplete="new-password" maxLength={LIMITS.passwordMax} invalid={!!errors.confirm && confirmValue.length > 0} {...register("confirm")} />
          {confirmValue && confirmValue === pwValue && <p role="status" className="mt-1 text-xs text-emerald-700">Passwords match</p>}
        </Field>
        <Button type="submit" loading={isSubmitting} className="w-full">Update password</Button>
      </form>
    </AuthLayout>
  );
}
