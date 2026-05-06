"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { ArrowUpRight, Filter } from "lucide-react";
import { useState } from "react";
import {
  api,
  type AnyPolicySummary,
  type AppFirewallSummary,
  type ApiDefinitionSummary,
  type BotDefensePolicySummary,
  type PolicyTypeUrl,
  type ServicePolicySummary,
  POLICY_TYPE_LABELS,
} from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { ActionBadge, EnforcementBadge, FeatureBadge, SharedScopeBadge } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";

type Scope = "all" | "shared" | "local";

export function PolicyListPage({ policyType }: { policyType: PolicyTypeUrl }) {
  const ready = useRequireAuth();
  const [scope, setScope] = useState<Scope>("all");

  const { data, isLoading } = useQuery({
    queryKey: ["policies", policyType, scope],
    queryFn: () =>
      api.listPolicies<AnyPolicySummary>(
        policyType,
        scope === "all" ? undefined : scope,
      ),
    enabled: ready,
  });

  if (!ready) return null;

  return (
    <Shell>
      <div className="px-8 py-8">
        <div className="mb-6 flex items-end justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
              Policies
            </div>
            <h1 className="font-display text-3xl font-semibold text-carbon-100">
              {POLICY_TYPE_LABELS[policyType]}
            </h1>
          </div>

          <div className="flex items-center gap-1 rounded border border-carbon-600 bg-carbon-800/60 p-1">
            <Filter size={12} className="ml-2 text-carbon-300" />
            {(["all", "shared", "local"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setScope(s)}
                className={cn(
                  "rounded px-2.5 py-1 font-mono text-[10px] uppercase tracking-widest transition-colors",
                  scope === s
                    ? "bg-accent-cyan text-carbon-900"
                    : "text-carbon-200 hover:bg-carbon-700",
                )}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Inventory</CardTitle>
            <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              {data ? `${data.length} ${scope === "all" ? "total" : scope}` : "—"}
            </span>
          </CardHeader>
          <CardBody className="!p-0">
            {isLoading ? (
              <div className="p-6 text-center text-xs text-carbon-300">Loading…</div>
            ) : !data || data.length === 0 ? (
              <div className="p-6 text-center text-xs text-carbon-300">
                No {POLICY_TYPE_LABELS[policyType]} policies in {scope === "all" ? "any" : scope} scope.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <PolicyTable policyType={policyType} rows={data} />
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </Shell>
  );
}

function PolicyTable({
  policyType,
  rows,
}: {
  policyType: PolicyTypeUrl;
  rows: AnyPolicySummary[];
}) {
  // Per-type column composition
  const columns =
    policyType === "app_firewalls" ? (
      <>
        <Th>Name</Th>
        <Th>Scope</Th>
        <Th>Mode</Th>
        <Th>Signatures</Th>
        <Th>Blocked attacks</Th>
        <Th>Custom rules</Th>
        <Th>Exclusions</Th>
        <Th align="right">Last seen</Th>
        <Th align="right" />
      </>
    ) : policyType === "service_policies" ? (
      <>
        <Th>Name</Th>
        <Th>Scope</Th>
        <Th>Default</Th>
        <Th>Rules</Th>
        <Th>Allow</Th>
        <Th>Deny</Th>
        <Th>Predicates</Th>
        <Th align="right">Last seen</Th>
        <Th align="right" />
      </>
    ) : policyType === "bot_defense_policies" ? (
      <>
        <Th>Name</Th>
        <Th>Scope</Th>
        <Th>Endpoints</Th>
        <Th>Mitigations</Th>
        <Th align="right">Last seen</Th>
        <Th align="right" />
      </>
    ) : (
      // api_definitions
      <>
        <Th>Name</Th>
        <Th>Scope</Th>
        <Th>Format</Th>
        <Th>Endpoints</Th>
        <Th>Validation</Th>
        <Th align="right">Last seen</Th>
        <Th align="right" />
      </>
    );

  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-carbon-600 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
          {columns}
        </tr>
      </thead>
      <tbody>
        {rows.map((p) => (
          <PolicyRow key={p.id} policyType={policyType} p={p} />
        ))}
      </tbody>
    </table>
  );
}

function PolicyRow({ policyType, p }: { policyType: PolicyTypeUrl; p: AnyPolicySummary }) {
  const detailHref = `/policies/${policyType}/${p.id}`;
  const lastSeen = formatDistanceToNow(new Date(p.last_seen_at), { addSuffix: true });

  return (
    <tr className="border-b border-carbon-700 transition-colors hover:bg-carbon-700/40">
      <td className="px-4 py-3 align-top">
        <div className="font-mono text-sm text-carbon-100">{p.name}</div>
        <div className="font-mono text-[10px] text-carbon-300">{p.namespace}</div>
      </td>
      <td className="px-4 py-3 align-top">
        <SharedScopeBadge shared={p.is_shared} />
      </td>

      {policyType === "app_firewalls" && <AppFirewallCells p={p as AppFirewallSummary} />}
      {policyType === "service_policies" && <ServicePolicyCells p={p as ServicePolicySummary} />}
      {policyType === "bot_defense_policies" && <BotDefenseCells p={p as BotDefensePolicySummary} />}
      {policyType === "api_definitions" && <ApiDefinitionCells p={p as ApiDefinitionSummary} />}

      <td className="px-4 py-3 text-right align-top font-mono text-xs text-carbon-300">{lastSeen}</td>
      <td className="px-4 py-3 text-right align-top">
        <Link
          href={detailHref}
          className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
        >
          detail <ArrowUpRight size={11} />
        </Link>
      </td>
    </tr>
  );
}

function AppFirewallCells({ p }: { p: AppFirewallSummary }) {
  return (
    <>
      <td className="px-4 py-3 align-top">
        <EnforcementBadge mode={p.enforcement_mode} />
      </td>
      <td className="px-4 py-3 align-top">
        <div className="flex flex-wrap gap-1">
          {p.enabled_signature_categories.length === 0 ? (
            <span className="font-mono text-[10px] text-carbon-300">—</span>
          ) : (
            <>
              {p.enabled_signature_categories.slice(0, 3).map((c) => (
                <span
                  key={c}
                  className="rounded border border-carbon-600 bg-carbon-800/50 px-1.5 py-0.5 font-mono text-[9px] text-carbon-100"
                >
                  {c}
                </span>
              ))}
              {p.enabled_signature_categories.length > 3 && (
                <span className="font-mono text-[9px] text-carbon-300">
                  +{p.enabled_signature_categories.length - 3}
                </span>
              )}
            </>
          )}
        </div>
      </td>
      <td className="px-4 py-3 align-top">
        <div className="flex flex-wrap gap-1">
          {p.blocked_attack_types.length === 0 ? (
            <span className="font-mono text-[10px] text-carbon-300">—</span>
          ) : (
            <>
              {p.blocked_attack_types.slice(0, 3).map((c) => (
                <span
                  key={c}
                  className="rounded border border-accent-red/30 bg-accent-red/5 px-1.5 py-0.5 font-mono text-[9px] text-accent-red"
                >
                  {c}
                </span>
              ))}
              {p.blocked_attack_types.length > 3 && (
                <span className="font-mono text-[9px] text-accent-red">
                  +{p.blocked_attack_types.length - 3}
                </span>
              )}
            </>
          )}
        </div>
      </td>
      <td className="px-4 py-3 align-top font-mono text-xs text-carbon-100">
        {p.custom_rule_count}
      </td>
      <td className="px-4 py-3 align-top font-mono text-xs text-carbon-100">
        {p.exclusion_rule_count}
      </td>
    </>
  );
}

function ServicePolicyCells({ p }: { p: ServicePolicySummary }) {
  return (
    <>
      <td className="px-4 py-3 align-top">
        <ActionBadge action={p.default_action} />
      </td>
      <td className="px-4 py-3 align-top font-mono text-xs text-carbon-100">{p.rule_count}</td>
      <td className="px-4 py-3 align-top font-mono text-xs text-accent-green">
        {p.allow_rule_count}
      </td>
      <td className="px-4 py-3 align-top font-mono text-xs text-accent-red">
        {p.deny_rule_count}
      </td>
      <td className="px-4 py-3 align-top">
        <div className="flex flex-wrap gap-1">
          <FeatureBadge enabled={p.has_geo_rules} label="GEO" tone="violet" />
          <FeatureBadge enabled={p.has_ip_rules} label="IP" tone="cyan" />
          <FeatureBadge enabled={p.has_path_rules} label="PATH" tone="amber" />
        </div>
      </td>
    </>
  );
}

function BotDefenseCells({ p }: { p: BotDefensePolicySummary }) {
  return (
    <>
      <td className="px-4 py-3 align-top font-mono text-xs text-carbon-100">
        {p.protected_endpoint_count}
      </td>
      <td className="px-4 py-3 align-top">
        <div className="flex flex-wrap gap-1">
          <FeatureBadge enabled={p.has_javascript_challenge} label="JS" tone="cyan" />
          <FeatureBadge enabled={p.has_captcha_challenge} label="CAPTCHA" tone="violet" />
          <FeatureBadge enabled={p.has_redirect} label="REDIRECT" tone="amber" />
          <FeatureBadge enabled={p.has_block} label="BLOCK" tone="green" />
        </div>
      </td>
    </>
  );
}

function ApiDefinitionCells({ p }: { p: ApiDefinitionSummary }) {
  return (
    <>
      <td className="px-4 py-3 align-top">
        {p.spec_format ? (
          <span className="rounded border border-carbon-600 bg-carbon-800/50 px-1.5 py-0.5 font-mono text-[10px] uppercase text-carbon-100">
            {p.spec_format}
          </span>
        ) : (
          <span className="font-mono text-[10px] text-carbon-300">—</span>
        )}
      </td>
      <td className="px-4 py-3 align-top font-mono text-xs text-carbon-100">{p.endpoint_count}</td>
      <td className="px-4 py-3 align-top">
        <FeatureBadge enabled={p.has_validation_rules} label="enforced" tone="green" />
      </td>
    </>
  );
}

function Th({ children, align = "left" }: { children?: React.ReactNode; align?: "left" | "right" }) {
  return (
    <th
      className={cn(
        "px-4 py-3 font-medium",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      {children}
    </th>
  );
}
