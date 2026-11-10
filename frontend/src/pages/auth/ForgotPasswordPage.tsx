import { useState } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import AuthLayout from "@/layouts/AuthLayout";
import { Alert, Button, Field, TextInput } from "@/components/ui";
import { api, errorMessage } from "@/services/api";

const schema = z.object({ email: z.string().min(1, "Enter your email").email("Enter a valid email") });

export default function ForgotPasswordPage() {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });

  const onSubmit = async (v: z.infer<typeof schema>) => {
    setError(null);
    try {
      const { data } = await api.post<{ message: string }>("/auth/forgot-password", v);
      setMessage(data.message);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <AuthLayout
      title="Forgot your password?"
      subtitle="Enter your email and we will send you a reset link."
      footer={<Link to="/login" className="font-medium text-brand-700 hover:underline">Back to sign in</Link>}
    >
      {message ? (
        <Alert kind="success">{message}</Alert>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          {error && <Alert kind="error">{error}</Alert>}
          <Field label="Email address" htmlFor="email" error={errors.email?.message}>
            <TextInput id="email" type="email" autoComplete="email" invalid={!!errors.email} {...register("email")} />
          </Field>
          <Button type="submit" loading={isSubmitting} className="w-full">Send reset link</Button>
        </form>
      )}
    </AuthLayout>
  );
}
