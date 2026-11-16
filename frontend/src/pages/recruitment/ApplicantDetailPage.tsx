import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Card, ErrorState, PageHeader, Spinner } from "@/components/ui";
import ProfileView from "@/components/ProfileView";
import type { Profile } from "@/types";

export default function ApplicantDetailPage() {
  const { id } = useParams();
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["applicant", id], queryFn: async () => (await api.get<Profile>(`/applicants/${id}`)).data });
  if (isLoading) return <Spinner />;
  if (error || !data) return <Card><ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /></Card>;
  return (
    <>
      <PageHeader title={data.full_name} description="Applicant profile (read-only)" actions={<Link to="/applicants" className="text-sm text-brand-700 hover:underline">← All applicants</Link>} />
      <ProfileView p={data} />
    </>
  );
}
