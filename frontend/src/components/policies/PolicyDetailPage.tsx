"use client";

import { useQuery, useQueries } from "@tanstack/react-query";
import { useMemo } from "react";
import Link from "next/link";
import { use } from "react";
import { ChevronLeft, ArrowUpRight } from "lucide-react";
import {
  api,
  type AnyPolicyDetail,
  type AppFirewallDetail,
  type ApiDefinitionDetail,
  type BotDefensePolicyDetail,
  type PolicyTypeUrl,
  type ServicePolicyDetail,
  POLICY_TYPE_LABELS,
} from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import {
  ActionBadge,
  EnforcementBadge,
  FeatureBadge,
  SharedScopeBadge,
} from "@/components/ui/Badge";
import { WafSparkline } from "@/components/analytics/WafSparkline";

export function PolicyDetailPage({
  policyType,
  params,
}: {
  policyType: PolicyTypeUrl;
  params: Promise<{ id: string }>;
}) {
  const ready = useRequireAuth();
  const { id } = use(params);
  const policy = useQuery({
    queryKey: ["policy", policyType, id],
    queryFn: () => api.getPolicy<AnyPolicyDetail>(policyType, id),
    enabled: ready,
  });

  if (!ready) return null;
  if (policy.isLoading) {
    return (
      <Shell>
        <div className="px-8 py-8 text-xs text-carbon-300">Loading…</div>
      </Shell>
    );
  }
  if (policy.error || !policy.data) {
    return (
      <Shell>
        <div className="px-8 py-8 text-xs text-accent-red">Policy not found.</div>
      </Shell>
    );
  }

  const p = policy.data;

  return (
    <Shell>
      <div className="px-8 py-8">
        <Link
          href={`/policies/${policyType}`}
          className="mb-3 inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-carbon-300 hover:text-accent-cyan"
        >
          <ChevronLeft size={12} /> back to {POLICY_TYPE_LABELS[policyType]}
        </Link>

        <div className="mb-6 flex items-end justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
              {POLICY_TYPE_LABELS[policyType]} · {p.namespace}
            </div>
            <div className="mt-1 flex items-center gap-3">
              <h1 className="font-display text-3xl font-semibold text-carbon-100">{p.name}</h1>
              <SharedScopeBadge shared={p.is_shared} />
            </div>
          </div>
        </div>

        {/* Per-type detail body */}
        <div className="grid gap-6 lg:grid-cols-3">
          {policyType === "app_firewalls" && <AppFirewallDetailBody p={p as AppFirewallDetail} />}
          {policyType === "service_policies" && (
            <ServicePolicyDetailBody p={p as ServicePolicyDetail} />
          )}
          {policyType === "bot_defense_policies" && (
            <BotDefenseDetailBody p={p as BotDefensePolicyDetail} />
          )}
          {policyType === "api_definitions" && (
            <ApiDefinitionDetailBody p={p as ApiDefinitionDetail} />
          )}
        </div>

        {/* Attached LBs (universal) */}
        <Card className="mt-6">
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Applied to</CardTitle>
            <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              {p.attached_to.length} load balancer{p.attached_to.length === 1 ? "" : "s"}
            </span>
          </CardHeader>
          <CardBody className="!p-0">
            {p.attached_to.length === 0 ? (
              <div className="p-6 text-center text-xs text-carbon-300">
                Not attached to any load balancers in this tenant.
              </div>
            ) : (
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-carbon-600 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                    <th className="px-4 py-3 font-medium">LB Name</th>
                    <th className="px-4 py-3 font-medium">Namespace</th>
                    <th className="px-4 py-3 text-right font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {p.attached_to.map((a) => (
                    <tr key={a.lb_id} className="border-b border-carbon-700 hover:bg-carbon-700/40">
                      <td className="px-4 py-3 font-mono text-sm text-carbon-100">{a.lb_name}</td>
                      <td className="px-4 py-3 font-mono text-xs text-carbon-200">
                        {a.lb_namespace}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Link
                          href={`/loadbalancers/${a.lb_id}`}
                          className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
                        >
                          open <ArrowUpRight size={11} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardBody>
        </Card>
      </div>
    </Shell>
  );
}

// ---------------- Per-type detail bodies ----------------

function AppFirewallDetailBody({ p }: { p: AppFirewallDetail }) {
  // Pull a sparkline per attached LB and sum them together for a per-policy view.
  // Each waf_policy can be attached to multiple LBs (one shared WAF guarding many),
  // and this aggregates traffic across every LB referencing this policy.
  const lbSparklines = useQueries({
    queries: p.attached_to.map((att) => ({
      queryKey: ["lb-waf-spark", att.lb_id],
      queryFn: () => api.wafSparkline({ lbId: att.lb_id, hours: 24 }),
      refetchInterval: 60_000,
    })),
  });
  const aggregated = useMemo(() => {
    // Bucket key = ISO bucket_time; sum request/blocked/monitored/error across LBs.
    const map = new Map<string, { request_count: number; blocked_count: number; monitored_count: number; error_count: number }>();
    let totalReq = 0;
    let totalBlk = 0;
    for (const q of lbSparklines) {
      if (!q.data) continue;
      for (const pt of q.data.points) {
        const cur = map.get(pt.bucket_time) ?? {
          request_count: 0, blocked_count: 0, monitored_count: 0, error_count: 0,
        };
        cur.request_count += pt.request_count;
        cur.blocked_count += pt.blocked_count;
        cur.monitored_count += pt.monitored_count;
        cur.error_count += pt.error_count;
        map.set(pt.bucket_time, cur);
      }
      totalReq += q.data.total_requests;
      totalBlk += q.data.total_blocked;
    }
    const points = Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([bucket_time, v]) => ({ bucket_time, ...v }));
    return { points, totalReq, totalBlk };
  }, [lbSparklines]);
  const allLoading = lbSparklines.length > 0 && lbSparklines.every((q) => q.isLoading);

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Enforcement</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <div>
            <Label>Mode</Label>
            <EnforcementBadge mode={p.enforcement_mode} />
          </div>
          <div>
            <Label>Detection</Label>
            <Mono>{p.detection_settings ?? "—"}</Mono>
          </div>
          <div>
            <Label>Default anonymization</Label>
            <Mono>{p.default_anonymization ?? "—"}</Mono>
          </div>
          <div>
            <Label>Default bot setting</Label>
            <Mono>{p.default_bot_setting ?? "—"}</Mono>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Signatures &amp; attacks</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <div>
            <Label>Enabled signature categories</Label>
            <BadgeList items={p.enabled_signature_categories} tone="cyan" empty="—" />
          </div>
          <div>
            <Label>Blocked attack types</Label>
            <BadgeList items={p.blocked_attack_types} tone="red" empty="—" />
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Counts</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <CountRow label="Custom rules" value={p.custom_rule_count} />
          <CountRow label="Exclusion rules" value={p.exclusion_rule_count} />
          <div>
            <Label>Allowed response codes</Label>
            <Mono>
              {p.allowed_response_codes && p.allowed_response_codes.length > 0
                ? p.allowed_response_codes.join(", ")
                : "—"}
            </Mono>
          </div>
        </CardBody>
      </Card>

      {/* Aggregated traffic across every LB attached to this WAF (slice 4) */}
      {p.attached_to.length > 0 && (
        <Card className="lg:col-span-3">
          <CardHeader className="flex items-center justify-between">
            <CardTitle>WAF traffic — last 24h (across {p.attached_to.length} LB{p.attached_to.length === 1 ? "" : "s"})</CardTitle>
            <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              <span className="text-accent-cyan">{aggregated.totalReq.toLocaleString()}</span>
              {" req · "}
              <span className="text-accent-red">{aggregated.totalBlk.toLocaleString()}</span>
              {" blocked"}
            </span>
          </CardHeader>
          <CardBody>
            {allLoading ? (
              <div className="h-[180px] text-center text-xs text-carbon-300">Loading…</div>
            ) : aggregated.points.length === 0 ? (
              <div className="h-[180px] text-center text-xs text-carbon-300">
                No traffic recorded for any of the attached LBs in the last 24h.
              </div>
            ) : (
              <WafSparkline points={aggregated.points} mode="twin" height={200} />
            )}
          </CardBody>
        </Card>
      )}
    </>
  );
}

function ServicePolicyDetailBody({ p }: { p: ServicePolicyDetail }) {
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Default action</CardTitle>
        </CardHeader>
        <CardBody>
          <ActionBadge action={p.default_action} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Rule counts</CardTitle>
        </CardHeader>
        <CardBody className="space-y-2">
          <CountRow label="Total rules" value={p.rule_count} />
          <CountRow label="Allow rules" value={p.allow_rule_count} valueClass="text-accent-green" />
          <CountRow label="Deny rules" value={p.deny_rule_count} valueClass="text-accent-red" />
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Predicates in use</CardTitle>
        </CardHeader>
        <CardBody>
          <div className="flex flex-wrap gap-1">
            <FeatureBadge enabled={p.has_geo_rules} label="GEO" tone="violet" />
            <FeatureBadge enabled={p.has_ip_rules} label="IP" tone="cyan" />
            <FeatureBadge enabled={p.has_path_rules} label="PATH" tone="amber" />
          </div>
        </CardBody>
      </Card>
    </>
  );
}

function BotDefenseDetailBody({ p }: { p: BotDefensePolicyDetail }) {
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Coverage</CardTitle>
        </CardHeader>
        <CardBody className="space-y-2">
          <CountRow label="Protected endpoints" value={p.protected_endpoint_count} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Mitigations enabled</CardTitle>
        </CardHeader>
        <CardBody>
          <div className="flex flex-wrap gap-1">
            <FeatureBadge enabled={p.has_javascript_challenge} label="JS" tone="cyan" />
            <FeatureBadge enabled={p.has_captcha_challenge} label="CAPTCHA" tone="violet" />
            <FeatureBadge enabled={p.has_redirect} label="REDIRECT" tone="amber" />
            <FeatureBadge enabled={p.has_block} label="BLOCK" tone="green" />
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Protected paths</CardTitle>
        </CardHeader>
        <CardBody>
          {p.protected_paths.length === 0 ? (
            <span className="font-mono text-[10px] text-carbon-300">—</span>
          ) : (
            <div className="flex flex-col gap-1">
              {p.protected_paths.map((path) => (
                <span
                  key={path}
                  className="rounded border border-carbon-600 bg-carbon-800/50 px-2 py-0.5 font-mono text-xs text-carbon-100"
                >
                  {path}
                </span>
              ))}
            </div>
          )}
        </CardBody>
      </Card>
    </>
  );
}

function ApiDefinitionDetailBody({ p }: { p: ApiDefinitionDetail }) {
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Specification</CardTitle>
        </CardHeader>
        <CardBody className="space-y-2">
          <div>
            <Label>Format</Label>
            <Mono>{p.spec_format ?? "—"}</Mono>
          </div>
          <CountRow label="Specs" value={p.api_specs_count} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Endpoints</CardTitle>
        </CardHeader>
        <CardBody>
          <CountRow label="Total endpoints" value={p.endpoint_count} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Validation</CardTitle>
        </CardHeader>
        <CardBody>
          <FeatureBadge enabled={p.has_validation_rules} label="rules enforced" tone="green" />
        </CardBody>
      </Card>
    </>
  );
}

// ---------------- Helpers ----------------

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1 font-mono text-[10px] uppercase tracking-widest text-carbon-300">
      {children}
    </div>
  );
}

function Mono({ children }: { children: React.ReactNode }) {
  return <div className="font-mono text-xs text-carbon-100">{children}</div>;
}

function CountRow({
  label,
  value,
  valueClass = "",
}: {
  label: string;
  value: number;
  valueClass?: string;
}) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
        {label}
      </span>
      <span
        className={`font-display text-2xl font-semibold tabular-nums text-carbon-100 ${valueClass}`}
      >
        {value}
      </span>
    </div>
  );
}

function BadgeList({
  items,
  tone,
  empty,
}: {
  items: string[];
  tone: "cyan" | "red";
  empty: string;
}) {
  if (items.length === 0)
    return <span className="font-mono text-[10px] text-carbon-300">{empty}</span>;
  const cls =
    tone === "red"
      ? "border-accent-red/30 bg-accent-red/5 text-accent-red"
      : "border-carbon-600 bg-carbon-800/50 text-carbon-100";
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((c) => (
        <span
          key={c}
          className={`rounded border px-1.5 py-0.5 font-mono text-[9px] ${cls}`}
        >
          {c}
        </span>
      ))}
    </div>
  );
}
