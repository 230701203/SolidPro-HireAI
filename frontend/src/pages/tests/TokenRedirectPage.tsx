import { Link, Navigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Alert, Card, Spinner } from "@/components/ui";
import type { Invitation } from "@/types";

/** Target of the emailed link. Sits behind login, so a forwarded link is useless to anyone but the invited applicant. */
export default function TokenRedirectPage() {
  const { token = "" } = useParams();
  const { data, error } = useQuery({ queryKey: ["invite-token", token], retry: false, queryFn: async () => (await api.get<Invitation>(`/test-invitations/by-token/${encodeURIComponent(token)}`)).data });
  if (data) return <Navigate to={`/my-tests/${data.id}`} replace />;
  if (error) {
    return (
      <div className="mx-auto max-w-md p-6">
        <Card className="p-6">
          <Alert kind="error">{errorMessage(error)}</Alert>
          <p className="mt-3 text-sm text-slate-600">Make sure you are logged in with the account you applied with. You can also find your tests under <Link className="text-brand-700 underline" to="/my-tests">My tests</Link>.</p>
        </Card>
      </div>
    );
  }
  return <Spinner label="Opening your invitation…" />;
}
