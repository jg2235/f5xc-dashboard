"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use } from "react";
import { ChevronLeft, ArrowUpRight } from "lucide-react";
import {
  api,
  POLICY_TYPE_LABELS,
  POLICY_TYPE_SHORT,
  type AttachedPolicyRef,
  type PolicyType,
  type PolicyTypeUrl,
} from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { FeatureBadge, SharedScopeBadge } from "@/components/ui/Badge";
import { HealthSummary } from "@/components/ui/HealthMatrix";
import { WafSparkline } from "@/components/analytics/WafSparkline";
import { BotSparkline } from "@/components/analytics/BotSparkline";
import { DiscoveryStateBadge } from "@/components/analytics/DiscoveryStateBadge";

const POLICY_TYPE_TO_URL: Record<PolicyType, PolicyTypeUrl> = {
  app_firewall: "app_firewalls",
  service_policy: "service_policies",
  bot_defense_policy: "bot_defense_policies",
  api_definition: "api_definitions",
};

export default function LBDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const ready = useRequireAuth();
  const { id } = use(params);
  const lb = useQuery({
    queryKey: ["lb", id],
    queryFn: () => api.getLoadBalancer(id),
    enabled: ready,
  });
  const policies = useQuery({
    queryKey: ["lb-policies", id],
    queryFn: () => api.getLoadBalancerPolicies(id),
    enabled: ready,
  });
  const wafSpark = useQuery({
    queryKey: ["lb-waf-spark", id],
    queryFn: () => api.wafSparkline({ lbId: id, hours: 24 }),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const botSpark = useQuery({
    queryKey: ["lb-bot-spark", id],
    queryFn: () => api.botSparkline({ lbId: id, hours: 24 }),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const apiEndpointsForLb = useQuery({
    queryKey: ["lb-api-endpoints", id],
    queryFn: () => api.apiEndpoints({ lbId: id, limit: 200 }),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const apiStateAll = useQuery({
    queryKey: ["api-discovery-state-list-for-lb"],
    queryFn: () => api.apiDiscoveryState(),
    enabled: ready,
    refetchInterval: 60_000,
  });

  if (!ready) return null;
  if (lb.isLoading) {
    return (
      <Shell>
        <div className="px-8 py-8 text-xs text-carbon-300">Loading…</div>
      </Shell>
    );
  }
  if (lb.error || !lb.data) {
    return (
      <Shell>
        <div className="px-8 py-8 text-xs text-accent-red">Load balancer not found.</div>
      </Shell>
    );
  }

  const x = lb.data;
  const policiesByType: Record<PolicyType, AttachedPolicyRef[]> = {
    app_firewall: [],
    service_policy: [],
    bot_defense_policy: [],
    api_definition: [],
  };
  for (const p of policies.data ?? []) {
    policiesByType[p.policy_type].push(p);
  }

  return (
    <Shell>
      <div className="px-8 py-8">
        <Link
          href="/loadbalancers"
          className="mb-3 inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-carbon-300 hover:text-accent-cyan"
        >
          <ChevronLeft size={12} /> back to load balancers
        </Link>
        <div className="mb-6 flex items-end justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
              {x.namespace} · {x.lb_type}
            </div>
            <h1 className="font-display text-3xl font-semibold text-carbon-100">{x.name}</h1>
            <div className="mt-1 flex flex-wrap gap-1 font-mono text-xs text-carbon-200">
              {x.domains.map((d) => (
                <span key={d} className="rounded bg-carbon-800 px-2 py-0.5">{d}</span>
              ))}
            </div>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <Card>
            <CardHeader><CardTitle>Capabilities</CardTitle></CardHeader>
            <CardBody>
              <div className="flex flex-wrap gap-1">
                <FeatureBadge enabled={x.has_waf} label="WAF" tone="cyan" />
                <FeatureBadge enabled={x.has_service_policy} label="SVC" tone="violet" />
                <FeatureBadge enabled={x.has_bot_defense} label="BOT" tone="green" />
                <FeatureBadge enabled={x.has_api_protection} label="API" tone="amber" />
              </div>
              <div className="mt-3 font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                See applied policies below for the actual references.
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader><CardTitle>Advertise</CardTitle></CardHeader>
            <CardBody>
              <div className="font-mono text-xs text-carbon-100">
                {x.advertise_mode?.replace(/_/g, " ") ?? "—"}
              </div>
              {x.advertised_sites.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {x.advertised_sites.map((s) => (
                    <span
                      key={s}
                      className="rounded border border-carbon-600 bg-carbon-800/50 px-2 py-0.5 font-mono text-[10px] text-carbon-100"
                    >
                      {s === "__all_re__" ? "all RE sites" : s}
                    </span>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader><CardTitle>TLS / Cert</CardTitle></CardHeader>
            <CardBody>
              {x.cert_ref ? (
                <div className="font-mono text-xs text-carbon-100">{x.cert_ref}</div>
              ) : x.lb_type === "https" ? (
                <div className="font-mono text-xs text-accent-cyan">auto-cert (managed)</div>
              ) : (
                <div className="font-mono text-xs text-carbon-300">no TLS</div>
              )}
            </CardBody>
          </Card>
        </div>

        {/* WAF traffic & violations (slice 4) */}
        {x.has_waf && (
          <Card className="mt-6">
            <CardHeader className="flex items-center justify-between">
              <CardTitle>WAF — last 24h</CardTitle>
              <Link
                href="/analytics/waf"
                className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
              >
                Tenant analytics <ArrowUpRight size={11} />
              </Link>
            </CardHeader>
            <CardBody>
              <div className="mb-3 flex items-center gap-6 font-mono text-xs">
                <span className="text-carbon-300">
                  Requests:{" "}
                  <span className="text-accent-cyan">
                    {wafSpark.data?.total_requests.toLocaleString() ?? "—"}
                  </span>
                </span>
                <span className="text-carbon-300">
                  Blocked:{" "}
                  <span className="text-accent-red">
                    {wafSpark.data?.total_blocked.toLocaleString() ?? "—"}
                  </span>
                </span>
                <span className="text-carbon-300">
                  Monitored:{" "}
                  <span className="text-accent-amber">
                    {wafSpark.data?.total_monitored.toLocaleString() ?? "—"}
                  </span>
                </span>
              </div>
              {wafSpark.isLoading ? (
                <div className="h-[160px] text-center text-xs text-carbon-300">Loading…</div>
              ) : (
                <WafSparkline points={wafSpark.data?.points ?? []} mode="twin" height={160} />
              )}
            </CardBody>
          </Card>
        )}

        {/* Bot traffic & interventions (slice 5) */}
        {x.has_bot_defense && (
          <Card className="mt-6">
            <CardHeader className="flex items-center justify-between">
              <CardTitle>Bot — last 24h</CardTitle>
              <Link
                href="/analytics/bot"
                className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
              >
                Tenant analytics <ArrowUpRight size={11} />
              </Link>
            </CardHeader>
            <CardBody>
              <div className="mb-3 flex items-center gap-6 font-mono text-xs">
                <span className="text-carbon-300">
                  Requests:{" "}
                  <span className="text-accent-cyan">
                    {botSpark.data?.total_requests.toLocaleString() ?? "—"}
                  </span>
                </span>
                <span className="text-carbon-300">
                  Challenges:{" "}
                  <span className="text-accent-amber">
                    {botSpark.data?.total_challenges.toLocaleString() ?? "—"}
                  </span>
                </span>
                <span className="text-carbon-300">
                  Blocks:{" "}
                  <span className="text-accent-red">
                    {botSpark.data?.total_blocks.toLocaleString() ?? "—"}
                  </span>
                </span>
              </div>
              {botSpark.isLoading ? (
                <div className="h-[160px] text-center text-xs text-carbon-300">Loading…</div>
              ) : (
                <BotSparkline points={botSpark.data?.points ?? []} mode="twin" height={160} />
              )}
            </CardBody>
          </Card>
        )}

        {/* API discovery (slice 6) */}
        {(() => {
          const epCount = apiEndpointsForLb.data?.length ?? 0;
          const shadowCount =
            apiEndpointsForLb.data?.filter((e) => e.is_shadow).length ?? 0;
          const lbState = apiStateAll.data?.find(
            (s) => s.lb_namespace === x.namespace && s.lb_name === x.name,
          );
          if (epCount === 0 && !lbState) return null;
          return (
            <Card className="mt-6">
              <CardHeader className="flex items-center justify-between">
                <CardTitle>API discovery</CardTitle>
                <Link
                  href="/analytics/api"
                  className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
                >
                  Tenant analytics <ArrowUpRight size={11} />
                </Link>
              </CardHeader>
              <CardBody>
                <div className="flex flex-wrap items-center gap-6 font-mono text-xs">
                  {lbState && (
                    <span className="text-carbon-300">
                      State:{" "}
                      <DiscoveryStateBadge
                        state={lbState.state}
                        confidence={lbState.confidence_score}
                      />
                    </span>
                  )}
                  <span className="text-carbon-300">
                    Endpoints discovered:{" "}
                    <span className="text-accent-cyan">{epCount}</span>
                  </span>
                  <span className="text-carbon-300">
                    Shadow:{" "}
                    <span className={shadowCount > 0 ? "text-accent-violet" : "text-accent-green"}>
                      {shadowCount}
                    </span>
                  </span>
                  {lbState && (
                    <span className="text-carbon-300">
                      Samples:{" "}
                      <span className="text-carbon-100">
                        {lbState.total_traffic_samples.toLocaleString()}
                      </span>
                    </span>
                  )}
                </div>
              </CardBody>
            </Card>
          );
        })()}

        {/* Applied policies */}
        <Card className="mt-6">
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Applied policies</CardTitle>
            <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              {policies.data?.length ?? 0} attached
            </span>
          </CardHeader>
          <CardBody>
            {policies.isLoading ? (
              <div className="text-center text-xs text-carbon-300">Loading…</div>
            ) : (policies.data?.length ?? 0) === 0 ? (
              <div className="text-center text-xs text-carbon-300">
                No policies attached to this load balancer.
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                {(["app_firewall", "service_policy", "bot_defense_policy", "api_definition"] as PolicyType[]).map(
                  (ptype) => {
                    const items = policiesByType[ptype];
                    if (items.length === 0) return null;
                    const url = POLICY_TYPE_TO_URL[ptype];
                    return (
                      <div
                        key={ptype}
                        className="rounded border border-carbon-600 bg-carbon-800/40 p-3"
                      >
                        <div className="mb-2 flex items-center justify-between">
                          <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-200">
                            {POLICY_TYPE_LABELS[url]}
                          </span>
                          <span className="font-mono text-[9px] uppercase tracking-widest text-carbon-300">
                            {POLICY_TYPE_SHORT[url]}
                          </span>
                        </div>
                        <div className="space-y-1">
                          {items.map((p) => {
                            const inner = (
                              <div className="flex items-center gap-2">
                                <SharedScopeBadge shared={p.is_shared} />
                                <span className="font-mono text-xs text-carbon-100">{p.policy_name}</span>
                                <span className="font-mono text-[10px] text-carbon-300">
                                  ({p.policy_namespace})
                                </span>
                                {p.policy_id && (
                                  <ArrowUpRight size={11} className="ml-auto text-accent-cyan" />
                                )}
                              </div>
                            );
                            const key = `${p.policy_type}-${p.policy_namespace}-${p.policy_name}`;
                            if (p.policy_id) {
                              return (
                                <Link
                                  key={key}
                                  href={`/policies/${url}/${p.policy_id}`}
                                  className="block rounded px-2 py-1 transition-colors hover:bg-carbon-700/40"
                                >
                                  {inner}
                                </Link>
                              );
                            }
                            return (
                              <div
                                key={key}
                                className="block rounded px-2 py-1"
                                title="Policy not yet synced — try Sync now"
                              >
                                {inner}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  },
                )}
              </div>
            )}
          </CardBody>
        </Card>

        {/* Origin pools */}
        <Card className="mt-6">
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Origin pools</CardTitle>
            <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              {x.pools.length} attached
            </span>
          </CardHeader>
          <CardBody className="!p-0">
            {x.pools.length === 0 ? (
              <div className="p-6 text-center text-xs text-carbon-300">
                No origin pools attached
              </div>
            ) : (
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-carbon-600 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                    <th className="px-4 py-3 font-medium">Name</th>
                    <th className="px-4 py-3 font-medium">Port</th>
                    <th className="px-4 py-3 font-medium">Origins</th>
                    <th className="px-4 py-3 font-medium">Health</th>
                    <th className="px-4 py-3 text-right font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {x.pools.map((p) => {
                    const total = p.healthy_count + p.unhealthy_count + p.warning_count;
                    return (
                      <tr key={p.id} className="border-b border-carbon-700 hover:bg-carbon-700/40">
                        <td className="px-4 py-3 font-mono text-sm text-carbon-100">{p.name}</td>
                        <td className="px-4 py-3 font-mono text-xs text-carbon-100">{p.port ?? "—"}</td>
                        <td className="px-4 py-3 font-mono text-xs text-carbon-100">{p.origin_count}</td>
                        <td className="px-4 py-3">
                          <HealthSummary
                            healthy={p.healthy_count}
                            unhealthy={p.unhealthy_count}
                            warning={p.warning_count}
                            total={total}
                          />
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Link
                            href={`/pools/${p.id}`}
                            className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
                          >
                            detail <ArrowUpRight size={11} />
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </CardBody>
        </Card>
      </div>
    </Shell>
  );
}
