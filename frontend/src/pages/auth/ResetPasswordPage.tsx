import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import AuthLayout from "@/layouts/AuthLayout";
import { Alert, Button, Field, PasswordInput } from "@/components/ui";
import { api, errorMessage, fieldErrors } from "@/services/api";
import { passwordSchema } from "@/utils/passwordRules";
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
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) });

  if (!token) {
    return (
      <AuthLayout title="Reset password" footer={<Link to="/forgot-password" className="font-medium text-brand-700 hover:underline">Request a new link</Link>}>
        <Alert kind="error">This reset link is incomplete.</Alert>
      </AuthLayout>
    );
  }

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
        <Field label="New password" htmlFor="new_password" error={errors.new_password?.message} hint="10+ characters with upper-case, lower-case and a number.">
          <PasswordInput id="new_password" autoComplete="new-password" invalid={!!errors.new_password} {...register("new_password")} />
        </Field>
        <Field label="Confirm new password" htmlFor="confirm" error={errors.confirm?.message}>
          <PasswordInput id="confirm" autoComplete="new-password" invalid={!!errors.confirm} {...register("confirm")} />
        </Field>
        <Button type="submit" loading={isSubmitting} className="w-full">Update password</Button>
      </form>
    </AuthLayout>
  );
}
