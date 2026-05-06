import { PolicyDetailPage } from "@/components/policies/PolicyDetailPage";
export default function Page({ params }: { params: Promise<{ id: string }> }) {
  return <PolicyDetailPage policyType="api_definitions" params={params} />;
}
