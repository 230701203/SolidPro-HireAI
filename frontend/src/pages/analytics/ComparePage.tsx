import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Alert, Badge, Card, ErrorState, PageHeader, Spinner, TableWrap, td, th } from "@/components/ui";
import type { CompareRow } from "@/types";

export default function ComparePage() {
  const [sp] = useSearchParams();
  const ids = (sp.get("ids") ?? "").split(",").filter(Boolean).map(Number).filter((n) => Number.isInteger(n));
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["compare", ids.join(",")],
    enabled: ids.length >= 2 && ids.length <= 5,
    queryFn: async () => (await api.get<CompareRow[]>("/analytics/compare", { params: { application_ids: ids }, paramsSerializer: { indexes: null } })).data,
  });
  if (ids.length < 2 || ids.length > 5) return <><PageHeader title="Compare candidates" /><Alert kind="warning">Choose between 2 and 5 results on the <Link to="/results" className="underline">Results page</Link>, then press Compare.</Alert></>;
  if (isLoading) return <Spinner />;
  if (error || !data) return <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} />;
  const sections = Array.from(new Set(data.flatMap((r) => r.sections.map((s) => s.section))));
  const row = (label: string, cell: (r: CompareRow) => React.ReactNode) => (
    <tr><th scope="row" className={`${th} text-left`}>{label}</th>{data.map((r) => <td key={r.application_id} className={`${td} align-top text-sm`}>{cell(r)}</td>)}</tr>
  );
  return (
    <>
      <PageHeader title="Compare candidates" description="A side-by-side view to support a human decision. Scores are advisory and do not rank or reject anyone." />
      <Card>
        <TableWrap>
          <thead><tr><th className={th} />{data.map((r) => <th key={r.application_id} className={th}><Link to={`/applications/${r.application_id}`} className="normal-case text-brand-700 hover:underline">{r.candidate_name}</Link></th>)}</tr></thead>
          <tbody>
            {row("Opening", (r) => r.opening_title)}
            {row("Status", (r) => r.status.replace("_", " "))}
            {row("Experience", (r) => (r.experience_years != null ? `${r.experience_years} years` : "—"))}
            {row("Match score", (r) => (r.match_score != null ? <>{r.match_score}/100 {r.match_is_mock && <Badge tone="amber">MOCK</Badge>}</> : "Not analysed"))}
            {row("Matched required skills", (r) => r.matched_required_skills.join(", ") || "—")}
            {row("Missing required skills", (r) => r.missing_required_skills.join(", ") || "—")}
            {row("Test score", (r) => (r.evaluation_percentage != null ? `${r.evaluation_percentage}%` : "No approved evaluation"))}
            {sections.map((s) => row(`Section: ${s.replace("_", " ")}`, (r) => { const x = r.sections.find((z) => z.section === s); return x ? `${x.obtained}/${x.total}` : "—"; }))}
          </tbody>
        </TableWrap>
      </Card>
    </>
  );
}
