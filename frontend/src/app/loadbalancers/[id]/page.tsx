"use client";

import { useQuery, useQueries } from "@tanstack/react-query";
import Link from "next/link";
import { use } from "react";
import { format, formatDistanceToNow } from "date-fns";
import { ChevronLeft, ArrowUpRight, FileJson } from "lucide-react";
import {
  api,
  POLICY_TYPE_LABELS,
  POLICY_TYPE_SHORT,
  type ApiDefinitionDetail,
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

  // Linked API definitions — fetch detail (swagger files + groups) for each
  // attached api_definition that has been synced (has a policy_id).
  const apiDefRefs = (policies.data ?? []).filter(
    (p) => p.policy_type === "api_definition" && p.policy_id,
  );
  const apiDefDetails = useQueries({
    queries: apiDefRefs.map((ref) => ({
      queryKey: ["api-def-detail", ref.policy_id],
      queryFn: () => api.getPolicy<ApiDefinitionDetail>("api_definitions", ref.policy_id!),
      enabled: ready,
    })),
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

        {/* API endpoints (slice 6) — only when the LB has API protection enabled.
            Mirrors F5 XC's Security Monitoring → API Endpoints screen. The
            "Inventory" rows are the declared operations from the linked API
            definition (api_groups); ML-discovered endpoints add traffic stats
            and surface "Shadow" endpoints not present in any definition. */}
        {x.has_api_protection && (() => {
          const discovered = apiEndpointsForLb.data ?? [];
          const discByKey = new Map(
            discovered.map((e) => [`${e.method} ${e.endpoint_path}`, e]),
          );

          type EpRow = {
            key: string;
            method: string;
            path: string;
            category: "Inventory" | "Shadow";
            defName: string | null;
            endpointId: string | null;
            authType: string | null;
            confidence: number | null;
            samples: number;
            codes: number[] | null;
            lastSeen: string | null;
          };
          const rows: EpRow[] = [];
          const seen = new Set<string>();

          // 1. Inventory operations declared in the linked API definition(s).
          //    Skip catch-all groups (regex path like ^/api/.*$).
          for (const d of apiDefDetails) {
            const detail = d.data;
            if (!detail) continue;
            for (const g of detail.api_groups ?? []) {
              for (const el of g.elements ?? []) {
                if (el.path_regex.includes(".*")) continue;
                for (const m of el.methods) {
                  const key = `${m} ${el.path_regex}`;
                  if (seen.has(key)) continue;
                  seen.add(key);
                  const disc = discByKey.get(key);
                  rows.push({
                    key,
                    method: m,
                    path: el.path_regex,
                    category: "Inventory",
                    defName: detail.name,
                    endpointId: disc?.id ?? null,
                    authType: disc?.auth_type ?? null,
                    confidence: disc?.discovery_confidence ?? null,
                    samples: disc?.total_request_samples ?? 0,
                    codes: disc?.response_codes ?? null,
                    lastSeen: disc?.last_seen_at ?? null,
                  });
                }
              }
            }
          }

          // 2. ML-discovered endpoints not present in any definition → Shadow.
          for (const e of discovered) {
            const key = `${e.method} ${e.endpoint_path}`;
            if (seen.has(key)) continue;
            seen.add(key);
            rows.push({
              key,
              method: e.method,
              path: e.endpoint_path,
              category: "Shadow",
              defName: e.api_definition_name,
              endpointId: e.id,
              authType: e.auth_type,
              confidence: e.discovery_confidence,
              samples: e.total_request_samples,
              codes: e.response_codes,
              lastSeen: e.last_seen_at,
            });
          }

          const total = rows.length;
          const inventoryCount = rows.filter((r) => r.category === "Inventory").length;
          const shadowCount = total - inventoryCount;
          const totalSamples = rows.reduce((sum, r) => sum + r.samples, 0);
          const authedCount = rows.filter(
            (r) => r.authType && r.authType !== "none" && r.authType !== "unknown",
          ).length;
          const lbState = apiStateAll.data?.find(
            (s) => s.lb_namespace === x.namespace && s.lb_name === x.name,
          );
          const loading =
            apiEndpointsForLb.isLoading || apiDefDetails.some((d) => d.isLoading);
          // Rows whose observed response codes fall in each status class.
          const classCount = (lo: number, hi: number) =>
            rows.filter((r) => (r.codes ?? []).some((c) => c >= lo && c < hi)).length;
          const statusClasses = [
            { label: "2xx", count: classCount(200, 300), tone: "text-accent-green" },
            { label: "3xx", count: classCount(300, 400), tone: "text-accent-cyan" },
            { label: "4xx", count: classCount(400, 500), tone: "text-accent-amber" },
            { label: "5xx", count: classCount(500, 600), tone: "text-accent-red" },
          ];
          return (
            <Card className="mt-6">
              <CardHeader className="flex items-center justify-between">
                <CardTitle>
                  <span className="inline-flex items-center gap-2">
                    API endpoints
                    {lbState && (
                      <DiscoveryStateBadge
                        state={lbState.state}
                        confidence={lbState.confidence_score}
                      />
                    )}
                  </span>
                </CardTitle>
                <Link
                  href="/analytics/api"
                  className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
                >
                  Tenant analytics <ArrowUpRight size={11} />
                </Link>
              </CardHeader>
              <CardBody>
                {/* Summary tiles */}
                <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
                  {[
                    { label: "Inventory", value: inventoryCount, tone: "text-accent-green" },
                    { label: "Shadow", value: shadowCount, tone: shadowCount > 0 ? "text-accent-violet" : "text-carbon-100" },
                    { label: "Total endpoints", value: total, tone: "text-accent-cyan" },
                    { label: "Total API calls", value: totalSamples.toLocaleString(), tone: "text-carbon-100" },
                  ].map((t) => (
                    <div
                      key={t.label}
                      className="rounded border border-carbon-600 bg-carbon-800/40 px-3 py-2"
                    >
                      <div className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                        {t.label}
                      </div>
                      <div className={`mt-1 font-display text-2xl font-semibold ${t.tone}`}>
                        {t.value}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Status-class + auth strip */}
                <div className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-2 font-mono text-xs text-carbon-300">
                  <span className="uppercase tracking-widest text-[10px]">Response classes:</span>
                  {statusClasses.map((s) => (
                    <span key={s.label}>
                      {s.label}: <span className={s.tone}>{s.count}</span>
                    </span>
                  ))}
                  <span className="ml-auto">
                    Authenticated:{" "}
                    <span className="text-accent-green">{authedCount}</span>
                    <span className="text-carbon-400"> / {total}</span>
                  </span>
                </div>

                {/* Endpoint table */}
                {loading ? (
                  <div className="py-6 text-center text-xs text-carbon-300">Loading…</div>
                ) : total === 0 ? (
                  <div className="py-6 text-center text-xs text-carbon-300">
                    No API endpoints found for this load balancer yet — wait for the next sync cycle.
                  </div>
                ) : (
                  <div className="overflow-x-auto rounded border border-carbon-700">
                    <table className="w-full border-collapse text-sm">
                      <thead>
                        <tr className="border-b border-carbon-600 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                          <th className="px-3 py-2 font-medium">API endpoint</th>
                          <th className="px-3 py-2 font-medium">Method</th>
                          <th className="px-3 py-2 font-medium">Auth</th>
                          <th className="px-3 py-2 font-medium">Category</th>
                          <th className="px-3 py-2 font-medium">Conf</th>
                          <th className="px-3 py-2 font-medium">Samples</th>
                          <th className="px-3 py-2 font-medium">Codes</th>
                          <th className="px-3 py-2 font-medium">Last seen</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((r) => (
                          <tr
                            key={r.key}
                            className="border-b border-carbon-700/50 last:border-0 hover:bg-carbon-700/40"
                          >
                            <td className="px-3 py-1.5">
                              {r.endpointId ? (
                                <Link
                                  href={`/analytics/api/endpoints/${r.endpointId}`}
                                  className="font-mono text-xs text-carbon-100 hover:text-accent-cyan"
                                >
                                  {r.path}
                                </Link>
                              ) : (
                                <span className="font-mono text-xs text-carbon-100">{r.path}</span>
                              )}
                            </td>
                            <td className="px-3 py-1.5">
                              <span className="rounded bg-carbon-700 px-1.5 py-0.5 font-mono text-[10px] uppercase text-carbon-100">
                                {r.method}
                              </span>
                            </td>
                            <td className="px-3 py-1.5 font-mono text-[11px] uppercase text-carbon-200">
                              {r.authType ?? "—"}
                            </td>
                            <td className="px-3 py-1.5">
                              {r.category === "Shadow" ? (
                                <span className="inline-flex items-center rounded border border-accent-violet/40 bg-accent-violet/10 px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-accent-violet">
                                  Shadow
                                </span>
                              ) : (
                                <span className="inline-flex items-center rounded border border-accent-green/30 bg-accent-green/10 px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-accent-green">
                                  Inventory
                                </span>
                              )}
                            </td>
                            <td className="px-3 py-1.5 font-mono text-[11px] tabular-nums text-carbon-100">
                              {r.confidence !== null ? `${r.confidence}%` : "—"}
                            </td>
                            <td className="px-3 py-1.5 font-mono text-[11px] tabular-nums text-carbon-100">
                              {r.samples.toLocaleString()}
                            </td>
                            <td className="px-3 py-1.5 font-mono text-[10px] text-carbon-200">
                              {r.codes && r.codes.length > 0 ? r.codes.join(", ") : "—"}
                            </td>
                            <td
                              className="px-3 py-1.5 font-mono text-[10px] text-carbon-300"
                              title={r.lastSeen ? format(new Date(r.lastSeen), "PPpp") : ""}
                            >
                              {r.lastSeen
                                ? formatDistanceToNow(new Date(r.lastSeen), { addSuffix: true })
                                : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardBody>
            </Card>
          );
        })()}

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


        {/* Linked API definitions — swagger spec files + group operations */}
        {apiDefRefs.map((ref, i) => {
          const detail = apiDefDetails[i]?.data;
          const loading = apiDefDetails[i]?.isLoading;
          const specFiles = detail?.swagger_spec_files ?? [];
          const groups = detail?.api_groups ?? [];
          return (
            <Card className="mt-6" key={`${ref.policy_namespace}-${ref.policy_name}`}>
              <CardHeader className="flex items-center justify-between">
                <CardTitle>
                  <span className="inline-flex items-center gap-2">
                    <FileJson size={14} className="text-accent-amber" />
                    API definition · {ref.policy_name}
                  </span>
                </CardTitle>
                <Link
                  href={`/policies/api_definitions/${ref.policy_id}`}
                  className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
                >
                  Definition detail <ArrowUpRight size={11} />
                </Link>
              </CardHeader>
              <CardBody className="space-y-5">
                {loading ? (
                  <div className="text-center text-xs text-carbon-300">Loading…</div>
                ) : (
                  <>
                    {/* Spec metadata strip */}
                    <div className="flex flex-wrap items-center gap-6 font-mono text-xs text-carbon-300">
                      <span>
                        Format:{" "}
                        <span className="text-carbon-100">{detail?.spec_format ?? "—"}</span>
                      </span>
                      <span>
                        Endpoints:{" "}
                        <span className="text-accent-cyan">{detail?.endpoint_count ?? 0}</span>
                      </span>
                      <span>
                        Schema strategy:{" "}
                        <span className="text-carbon-100">
                          {detail?.schema_update_strategy ?? "—"}
                        </span>
                      </span>
                    </div>

                    {/* OpenAPI / swagger spec files */}
                    <div>
                      <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                        OpenAPI specification files ({specFiles.length})
                      </div>
                      {specFiles.length === 0 ? (
                        <div className="font-mono text-[10px] text-carbon-300">
                          No specification files referenced.
                        </div>
                      ) : (
                        <div className="flex flex-col gap-1">
                          {specFiles.map((f) => (
                            <span
                              key={f}
                              className="break-all rounded border border-carbon-600 bg-carbon-800/50 px-2 py-1 font-mono text-xs text-carbon-100"
                            >
                              {f}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* API groups → operations */}
                    <div>
                      <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                        Api groups ({groups.length})
                      </div>
                      {groups.length === 0 ? (
                        <div className="font-mono text-[10px] text-carbon-300">
                          No API groups defined.
                        </div>
                      ) : (
                        <div className="space-y-4">
                          {groups.map((g) => (
                            <div key={g.name}>
                              <div className="mb-2 flex items-center justify-between">
                                <span className="font-mono text-xs text-accent-cyan">{g.name}</span>
                                <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                                  {g.element_count} element{g.element_count === 1 ? "" : "s"}
                                </span>
                              </div>
                              {g.elements.length > 0 && (
                                <div className="overflow-hidden rounded border border-carbon-600">
                                  <table className="w-full text-left">
                                    <thead>
                                      <tr className="border-b border-carbon-600 bg-carbon-800/50">
                                        <th className="px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                                          Methods
                                        </th>
                                        <th className="px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                                          Path regex
                                        </th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {g.elements.map((el, j) => (
                                        <tr
                                          key={`${el.path_regex}-${j}`}
                                          className="border-b border-carbon-700/50 last:border-0"
                                        >
                                          <td className="px-3 py-1.5 align-top">
                                            <div className="flex flex-wrap gap-1">
                                              {el.methods.map((m) => (
                                                <span
                                                  key={m}
                                                  className="rounded border border-carbon-600 bg-carbon-800/50 px-1.5 py-0.5 font-mono text-[10px] text-carbon-100"
                                                >
                                                  {m}
                                                </span>
                                              ))}
                                            </div>
                                          </td>
                                          <td className="px-3 py-1.5 font-mono text-xs text-carbon-100">
                                            {el.path_regex}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </>
                )}
              </CardBody>
            </Card>
          );
        })}

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
