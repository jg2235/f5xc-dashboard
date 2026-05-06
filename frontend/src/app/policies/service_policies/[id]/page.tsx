import { PolicyDetailPage } from "@/components/policies/PolicyDetailPage";
export default function Page({ params }: { params: Promise<{ id: string }> }) {
  return <PolicyDetailPage policyType="service_policies" params={params} />;
}
