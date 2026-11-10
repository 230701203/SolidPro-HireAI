import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, XCircle } from "lucide-react";
import AuthLayout from "@/layouts/AuthLayout";
import { Spinner } from "@/components/ui";
import { api, errorMessage } from "@/services/api";

export default function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [state, setState] = useState<{ ok: boolean; message: string } | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return; // StrictMode runs effects twice; verify once
    started.current = true;
    if (!token) {
      setState({ ok: false, message: "This verification link is incomplete." });
      return;
    }
    api
      .post<{ message: string }>("/auth/verify-email", { token })
      .then((r) => setState({ ok: true, message: r.data.message }))
      .catch((e) => setState({ ok: false, message: errorMessage(e) }));
  }, [token]);

  return (
    <AuthLayout title="Email verification">
      {!state ? (
        <Spinner label="Verifying…" />
      ) : (
        <div className="flex flex-col items-center gap-4 text-center">
          {state.ok ? <CheckCircle2 className="size-12 text-emerald-600" /> : <XCircle className="size-12 text-red-500" />}
          <p className="text-sm text-slate-700">{state.message}</p>
          <Link to="/login" className="rounded-lg bg-brand-700 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-800">Go to sign in</Link>
        </div>
      )}
    </AuthLayout>
  );
}
