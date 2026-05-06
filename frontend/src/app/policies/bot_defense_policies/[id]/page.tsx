import { PolicyDetailPage } from "@/components/policies/PolicyDetailPage";
export default function Page({ params }: { params: Promise<{ id: string }> }) {
  return <PolicyDetailPage policyType="bot_defense_policies" params={params} />;
}
