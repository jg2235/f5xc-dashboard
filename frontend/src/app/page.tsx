"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { api, POLICY_TYPE_LABELS, type PolicyTypeUrl } from "@/lib/api";
import { WafSparkline } from "@/components/analytics/WafSparkline";
import { BotSparkline } from "@/components/analytics/BotSparkline";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { StatCard } from "@/components/ui/StatCard";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";

const CERT_COLORS: Record<string, string> = {
  ok: "#32d296",
  warn: "#ffb547",
  critical: "#ff4d6d",
  expired: "#6a1a2a",
};

const POLICY_TYPES: { url: PolicyTypeUrl; key: keyof Awaited<ReturnType<typeof api.policyStats>> }[] = [
  { url: "app_firewalls", key: "app_firewall" },
  { url: "service_policies", key: "service_policy" },
  { url: "bot_defense_policies", key: "bot_defense_policy" },
  { url: "api_definitions", key: "api_definition" },
];

export default function OverviewPage() {
  const ready = useRequireAuth();
  const lbStats = useQuery({ queryKey: ["lb-stats"], queryFn: api.lbStats, enabled: ready });
  const certStats = useQuery({ queryKey: ["cert-stats"], queryFn: api.certStats, enabled: ready });
  const poolStats = useQuery({ queryKey: ["pool-stats"], queryFn: api.poolStats, enabled: ready });
  const policyStats = useQuery({ queryKey: ["policy-stats"], queryFn: api.policyStats, enabled: ready });
  const wafOverview = useQuery({
    queryKey: ["waf-overview-24h"],
    queryFn: () => api.wafOverview(60 * 24),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const wafSpark = useQuery({
    queryKey: ["waf-spark-24h"],
    queryFn: () => api.wafSparkline({ hours: 24 }),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const botOverview = useQuery({
    queryKey: ["bot-overview-24h"],
    queryFn: () => api.botOverview(60 * 24),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const botSpark = useQuery({
    queryKey: ["bot-spark-24h"],
    queryFn: () => api.botSparkline({ hours: 24 }),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const apiOverview = useQuery({
    queryKey: ["api-overview-24h"],
    queryFn: () => api.apiOverview(60 * 24),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const apiDiscovery = useQuery({
    queryKey: ["api-discovery-state-overview"],
    queryFn: () => api.apiDiscoveryState(),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const securityOverview = useQuery({
    queryKey: ["security-overview-card"],
    queryFn: () => api.securityOverview(60 * 24),
    enabled: ready,
    refetchInterval: 60_000,
  });

  if (!ready) return null;

  const certData =
    certStats.data !== undefined
      ? [
          { name: "OK", value: certStats.data.ok, key: "ok" },
          { name: "Warn", value: certStats.data.warn, key: "warn" },
          { name: "Critical", value: certStats.data.critical, key: "critical" },
          { name: "Expired", value: certStats.data.expired, key: "expired" },
        ].filter((d) => d.value > 0)
      : [];

  return (
    <Shell>
      <div className="px-8 py-8">
        <div className="mb-6 flex items-end justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
              Tenant overview
            </div>
            <h1 className="font-display text-3xl font-semibold text-carbon-100">Dashboard</h1>
          </div>
        </div>

        {/* LB-centric */}
        <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Load balancers" value={lbStats.data?.total ?? "—"} tone="info" />
          <StatCard
            label="WAF enabled"
            value={lbStats.data?.with_waf ?? "—"}
            sub={
              lbStats.data
                ? `${Math.round((lbStats.data.with_waf / Math.max(lbStats.data.total, 1)) * 100)}% of LBs`
                : undefined
            }
            tone="ok"
          />
          <StatCard label="Bot defense" value={lbStats.data?.with_bot_defense ?? "—"} tone="ok" />
          <StatCard label="API protection" value={lbStats.data?.with_api_protection ?? "—"} tone="ok" />
        </div>

        {/* Pool-centric */}
        <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Origin pools" value={poolStats.data?.total_pools ?? "—"} />
          <StatCard label="Total origins" value={poolStats.data?.total_origins ?? "—"} />
          <StatCard
            label="Unhealthy origin × site"
            value={poolStats.data?.unhealthy_cells ?? "—"}
            tone={poolStats.data && poolStats.data.unhealthy_cells > 0 ? "critical" : "ok"}
          />
          <StatCard
            label="Origin × site warnings"
            value={poolStats.data?.warning_cells ?? "—"}
            tone={poolStats.data && poolStats.data.warning_cells > 0 ? "warn" : "ok"}
          />
        </div>

        {/* Policy-centric (slice 3) */}
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          {POLICY_TYPES.map((t) => {
            const s = policyStats.data?.[t.key];
            const total = s?.total ?? 0;
            const unattached = s?.unattached ?? 0;
            return (
              <Link key={t.url} href={`/policies/${t.url}`} className="block">
                <div className="rounded-lg border border-carbon-600 bg-carbon-800/60 p-5 transition-colors hover:border-accent-cyan/30">
                  <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-carbon-300">
                    {POLICY_TYPE_LABELS[t.url]}
                  </div>
                  <div className="mt-2 font-display text-3xl font-semibold tabular-nums text-carbon-100">
                    {policyStats.data ? total : "—"}
                  </div>
                  {policyStats.data && (
                    <div className="mt-1 flex items-center justify-between font-mono text-[10px]">
                      <span className="text-accent-violet">{s?.shared ?? 0} shared</span>
                      <span className="text-accent-cyan">{s?.local ?? 0} local</span>
                      {unattached > 0 && (
                        <span className="text-accent-amber">{unattached} unattached</span>
                      )}
                    </div>
                  )}
                </div>
              </Link>
            );
          })}
        </div>

        {/* WAF analytics hero (slice 4) */}
        <Card className="mb-6">
          <CardHeader className="flex items-center justify-between">
            <CardTitle>WAF — last 24h</CardTitle>
            <Link
              href="/analytics/waf"
              className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
            >
              View analytics <ArrowUpRight size={12} />
            </Link>
          </CardHeader>
          <CardBody>
            <div className="grid gap-4 lg:grid-cols-4">
              <div className="space-y-3 lg:col-span-1">
                <HeroStat
                  label="Requests"
                  value={wafOverview.data?.total_requests ?? "—"}
                  tone="info"
                />
                <HeroStat
                  label="Blocked"
                  value={wafOverview.data?.total_blocked ?? "—"}
                  tone={
                    wafOverview.data && wafOverview.data.total_blocked > 0 ? "critical" : "ok"
                  }
                />
                <HeroStat
                  label="Block rate"
                  value={wafOverview.data ? `${wafOverview.data.block_rate_pct}%` : "—"}
                  tone={
                    wafOverview.data && wafOverview.data.block_rate_pct > 5 ? "critical" : "ok"
                  }
                />
              </div>
              <div className="lg:col-span-3">
                {wafSpark.isLoading ? (
                  <div className="flex h-[200px] items-center justify-center text-xs text-carbon-300">
                    Loading…
                  </div>
                ) : (
                  <WafSparkline points={wafSpark.data?.points ?? []} mode="twin" height={200} />
                )}
              </div>
            </div>
          </CardBody>
        </Card>

        {/* Bot analytics hero (slice 5) */}
        <Card className="mb-6">
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Bot — last 24h</CardTitle>
            <Link
              href="/analytics/bot"
              className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
            >
              View analytics <ArrowUpRight size={12} />
            </Link>
          </CardHeader>
          <CardBody>
            <div className="grid gap-4 lg:grid-cols-4">
              <div className="space-y-3 lg:col-span-1">
                <HeroStat
                  label="Requests"
                  value={botOverview.data?.total_requests ?? "—"}
                  tone="info"
                />
                <HeroStat
                  label="Challenges"
                  value={botOverview.data?.total_challenges ?? "—"}
                  tone={botOverview.data && botOverview.data.total_challenges > 0 ? "warn" : "ok"}
                />
                <HeroStat
                  label="Blocks"
                  value={botOverview.data?.total_blocks ?? "—"}
                  tone={botOverview.data && botOverview.data.total_blocks > 0 ? "critical" : "ok"}
                />
              </div>
              <div className="lg:col-span-3">
                {botSpark.isLoading ? (
                  <div className="flex h-[200px] items-center justify-center text-xs text-carbon-300">
                    Loading…
                  </div>
                ) : (
                  <BotSparkline points={botSpark.data?.points ?? []} mode="twin" height={200} />
                )}
              </div>
            </div>
          </CardBody>
        </Card>

        {/* API analytics hero (slice 6) */}
        <Card className="mb-6">
          <CardHeader className="flex items-center justify-between">
            <CardTitle>API discovery & inventory</CardTitle>
            <Link
              href="/analytics/api"
              className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
            >
              View analytics <ArrowUpRight size={12} />
            </Link>
          </CardHeader>
          <CardBody>
            <div className="grid gap-4 lg:grid-cols-4">
              <HeroStat
                label="Endpoints discovered"
                value={apiOverview.data?.total_endpoints ?? "—"}
                tone="info"
              />
              <HeroStat
                label="Shadow endpoints"
                value={apiOverview.data?.shadow_endpoints ?? "—"}
                tone={apiOverview.data && apiOverview.data.shadow_endpoints > 0 ? "warn" : "ok"}
              />
              <HeroStat
                label="Avg p99 latency"
                value={
                  apiOverview.data?.avg_p99_latency_ms !== null && apiOverview.data?.avg_p99_latency_ms !== undefined
                    ? `${apiOverview.data.avg_p99_latency_ms} ms`
                    : "—"
                }
                tone={
                  apiOverview.data && (apiOverview.data.avg_p99_latency_ms ?? 0) > 500 ? "warn" : "ok"
                }
              />
              <HeroStat
                label="Error rate"
                value={apiOverview.data ? `${apiOverview.data.error_rate_pct}%` : "—"}
                tone={apiOverview.data && apiOverview.data.error_rate_pct > 5 ? "critical" : "ok"}
              />
            </div>
            {/* Discovery state distribution: small inline summary */}
            {apiDiscovery.data && apiDiscovery.data.length > 0 && (
              <div className="mt-4 flex flex-wrap items-center gap-3 font-mono text-xs">
                <span className="text-carbon-300">ML state:</span>
                {Object.entries(apiOverview.data?.state_counts ?? {}).map(([state, count]) => (
                  <span
                    key={state}
                    className="inline-flex items-center gap-1 rounded border border-carbon-600 bg-carbon-800/40 px-2 py-0.5 text-[10px] uppercase"
                  >
                    <span className="text-carbon-200">{state}</span>
                    <span className="text-accent-cyan">{count}</span>
                  </span>
                ))}
              </div>
            )}
          </CardBody>
        </Card>

        {/* Security analytics hero (slice 7) */}
        <Card className="mb-6">
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Security posture</CardTitle>
            <div className="flex items-center gap-3">
              <Link
                href="/alerts"
                className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
              >
                Alerts <ArrowUpRight size={12} />
              </Link>
              <Link
                href="/analytics/security"
                className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
              >
                View analytics <ArrowUpRight size={12} />
              </Link>
            </div>
          </CardHeader>
          <CardBody>
            <div className="grid gap-4 lg:grid-cols-4">
              <HeroStat
                label="Active attackers"
                value={securityOverview.data?.total_attackers ?? "—"}
                tone={
                  securityOverview.data && securityOverview.data.total_attackers > 0
                    ? "warn"
                    : "ok"
                }
              />
              <HeroStat
                label="Top country"
                value={
                  securityOverview.data?.top_country
                    ? `${securityOverview.data.top_country} · ${securityOverview.data.top_country_count}`
                    : "—"
                }
                tone="info"
              />
              <HeroStat
                label="Open alerts"
                value={securityOverview.data?.open_alerts ?? "—"}
                tone={
                  securityOverview.data && securityOverview.data.open_alerts > 0
                    ? "warn"
                    : "ok"
                }
              />
              <HeroStat
                label="Critical alerts"
                value={securityOverview.data?.critical_alerts ?? "—"}
                tone={
                  securityOverview.data && securityOverview.data.critical_alerts > 0
                    ? "critical"
                    : "ok"
                }
              />
            </div>
            {/* Activity summary */}
            {securityOverview.data && (
              <div className="mt-4 flex flex-wrap items-center gap-3 font-mono text-xs">
                <span className="text-carbon-300">Last 24h:</span>
                <span className="inline-flex items-center gap-1 rounded border border-carbon-600 bg-carbon-800/40 px-2 py-0.5 text-[10px]">
                  <span className="text-carbon-200">WAF blocks</span>
                  <span className="text-accent-red">
                    {securityOverview.data.total_waf_blocks.toLocaleString()}
                  </span>
                </span>
                <span className="inline-flex items-center gap-1 rounded border border-carbon-600 bg-carbon-800/40 px-2 py-0.5 text-[10px]">
                  <span className="text-carbon-200">Bot interventions</span>
                  <span className="text-accent-amber">
                    {securityOverview.data.total_bot_interventions.toLocaleString()}
                  </span>
                </span>
                <span className="inline-flex items-center gap-1 rounded border border-carbon-600 bg-carbon-800/40 px-2 py-0.5 text-[10px]">
                  <span className="text-carbon-200">Countries</span>
                  <span className="text-accent-cyan">
                    {securityOverview.data.countries_seen}
                  </span>
                </span>
              </div>
            )}
          </CardBody>
        </Card>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-1">
            <CardHeader className="flex items-center justify-between">
              <CardTitle>Certificate status</CardTitle>
              <Link
                href="/certificates"
                className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
              >
                View all <ArrowUpRight size={12} />
              </Link>
            </CardHeader>
            <CardBody>
              {certStats.data === undefined ? (
                <div className="flex h-48 items-center justify-center text-xs text-carbon-300">loading…</div>
              ) : certData.length === 0 ? (
                <div className="flex h-48 items-center justify-center text-xs text-carbon-300">
                  No certificates found
                </div>
              ) : (
                <>
                  <div className="h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={certData}
                          dataKey="value"
                          innerRadius={45}
                          outerRadius={75}
                          paddingAngle={2}
                          strokeWidth={0}
                        >
                          {certData.map((entry) => (
                            <Cell key={entry.key} fill={CERT_COLORS[entry.key]} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            background: "#0d1520",
                            border: "1px solid #2a3142",
                            borderRadius: 6,
                            fontSize: 12,
                          }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                    {certData.map((d) => (
                      <div key={d.key} className="flex items-center gap-2">
                        <span
                          className="inline-block h-2 w-2 rounded-full"
                          style={{ background: CERT_COLORS[d.key] }}
                        />
                        <span className="text-carbon-300">{d.name}</span>
                        <span className="ml-auto font-mono text-carbon-100">{d.value}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </CardBody>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>LB coverage</CardTitle>
            </CardHeader>
            <CardBody>
              {lbStats.data === undefined ? (
                <div className="flex h-48 items-center justify-center text-xs text-carbon-300">loading…</div>
              ) : (
                <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
                  <CoverageBar label="HTTPS" value={lbStats.data.https} total={lbStats.data.total} />
                  <CoverageBar label="HTTP only" value={lbStats.data.http_only} total={lbStats.data.total} tone="warn" />
                  <CoverageBar label="Service policy" value={lbStats.data.with_service_policy} total={lbStats.data.total} />
                  <CoverageBar label="WAF" value={lbStats.data.with_waf} total={lbStats.data.total} />
                  <CoverageBar label="Bot defense" value={lbStats.data.with_bot_defense} total={lbStats.data.total} />
                  <CoverageBar label="API protection" value={lbStats.data.with_api_protection} total={lbStats.data.total} />
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </Shell>
  );
}

function CoverageBar({
  label,
  value,
  total,
  tone = "ok",
}: {
  label: string;
  value: number;
  total: number;
  tone?: "ok" | "warn";
}) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  const color = tone === "warn" ? "bg-accent-amber" : "bg-accent-cyan";
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">{label}</span>
        <span className="font-display text-lg font-semibold tabular-nums text-carbon-100">
          {value}
          <span className="ml-1 text-xs font-normal text-carbon-300">/ {total}</span>
        </span>
      </div>
      <div className="mt-1.5 h-1 w-full overflow-hidden rounded bg-carbon-700">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}


function HeroStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone: "ok" | "warn" | "critical" | "info";
}) {
  const cls = tone === "critical"
    ? "text-accent-red"
    : tone === "warn"
    ? "text-accent-amber"
    : tone === "info"
    ? "text-accent-cyan"
    : "text-accent-green";
  return (
    <div className="rounded border border-carbon-600 bg-carbon-800/40 px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">{label}</div>
      <div className={`font-display text-2xl font-semibold tabular-nums ${cls}`}>
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
    </div>
  );
}
