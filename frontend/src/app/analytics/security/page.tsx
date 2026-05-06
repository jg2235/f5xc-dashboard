"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { format, formatDistanceToNow } from "date-fns";
import { useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { GeoChoropleth } from "@/components/analytics/GeoChoropleth";
import { AlertSeverityBadge, AlertStatusBadge } from "@/components/analytics/AlertBadges";
import { cn } from "@/lib/cn";

type SortOption = "total" | "waf" | "bot" | "last_seen";

export default function SecurityAnalyticsPage() {
  const ready = useRequireAuth();
  const [hours, setHours] = useState<number>(24);
  const [sort, setSort] = useState<SortOption>("total");

  const overview = useQuery({
    queryKey: ["security-overview", hours * 60],
    queryFn: () => api.securityOverview(hours * 60),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const geo = useQuery({
    queryKey: ["security-geo", hours],
    queryFn: () => api.securityGeo({ hours }),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const attackers = useQuery({
    queryKey: ["security-attackers", sort],
    queryFn: () => api.securityAttackers({ limit: 50, sort }),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const recentAlerts = useQuery({
    queryKey: ["security-recent-alerts"],
    queryFn: () => api.listAlerts({ status: "open", limit: 10 }),
    enabled: ready,
    refetchInterval: 30_000,
  });

  if (!ready) return null;

  return (
    <Shell>
      <div className="px-8 py-8">
        <div className="mb-6 flex items-end justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
              Analytics · Security
            </div>
            <h1 className="font-display text-3xl font-semibold text-carbon-100">
              Security Analytics
            </h1>
            <div className="mt-1 font-mono text-xs text-carbon-300">
              Cross-signal threat view — WAF, Bot, and API events correlated by source IP.
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/alerts"
              className="inline-flex items-center gap-1 rounded border border-carbon-600 px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:bg-carbon-700"
            >
              View alerts <ArrowUpRight size={11} />
            </Link>
            <div className="flex items-center gap-1 rounded border border-carbon-600 bg-carbon-800/60 p-1">
              {[1, 6, 24, 168].map((h) => (
                <button
                  key={h}
                  onClick={() => setHours(h)}
                  className={cn(
                    "rounded px-2.5 py-1 font-mono text-[10px] uppercase tracking-widest transition-colors",
                    hours === h
                      ? "bg-accent-cyan text-carbon-900"
                      : "text-carbon-200 hover:bg-carbon-700",
                  )}
                >
                  {h === 168 ? "7d" : `${h}h`}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Hero stats */}
        <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard
            label="Active attackers"
            value={overview.data?.total_attackers ?? "—"}
            tone={
              overview.data && overview.data.total_attackers > 0 ? "warn" : "ok"
            }
          />
          <StatCard
            label="WAF blocks"
            value={overview.data?.total_waf_blocks ?? "—"}
            tone={
              overview.data && overview.data.total_waf_blocks > 0 ? "critical" : "ok"
            }
          />
          <StatCard
            label="Bot interventions"
            value={overview.data?.total_bot_interventions ?? "—"}
            tone={
              overview.data && overview.data.total_bot_interventions > 0 ? "warn" : "ok"
            }
          />
          <StatCard
            label="Open alerts"
            value={overview.data?.open_alerts ?? "—"}
            tone={
              overview.data && overview.data.critical_alerts > 0
                ? "critical"
                : overview.data && overview.data.open_alerts > 0
                ? "warn"
                : "ok"
            }
          />
        </div>

        {/* Geo + Recent alerts side-by-side */}
        <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader className="flex items-center justify-between">
              <CardTitle>Attack origin by country</CardTitle>
              <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                {overview.data?.countries_seen ?? 0} countries · last {hours}h
              </span>
            </CardHeader>
            <CardBody>
              {geo.isLoading ? (
                <div className="h-[320px] text-center text-xs text-carbon-300">Loading…</div>
              ) : (
                <GeoChoropleth entries={geo.data ?? []} height={320} />
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader className="flex items-center justify-between">
              <CardTitle>Open alerts</CardTitle>
              <Link
                href="/alerts"
                className="font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
              >
                view all
              </Link>
            </CardHeader>
            <CardBody className="!p-0">
              {recentAlerts.isLoading ? (
                <div className="p-6 text-center text-xs text-carbon-300">Loading…</div>
              ) : (recentAlerts.data?.length ?? 0) === 0 ? (
                <div className="p-6 text-center text-xs text-accent-green">
                  ✓ no open alerts
                </div>
              ) : (
                <ul className="divide-y divide-carbon-700">
                  {recentAlerts.data!.slice(0, 8).map((a) => (
                    <li key={a.id} className="px-4 py-2.5 hover:bg-carbon-700/40">
                      <Link href={`/alerts/${a.id}`} className="block">
                        <div className="mb-1 flex items-center gap-2">
                          <AlertSeverityBadge severity={a.severity} />
                          <span className="font-mono text-[9px] text-carbon-300">
                            {a.rule_id}
                          </span>
                        </div>
                        <div
                          className="line-clamp-2 text-xs text-carbon-100"
                          title={a.title}
                        >
                          {a.title}
                        </div>
                        <div className="mt-1 font-mono text-[10px] text-carbon-300">
                          {formatDistanceToNow(new Date(a.last_seen_at), { addSuffix: true })}
                          {a.occurrence_count > 1 && (
                            <span className="ml-2 text-accent-amber">
                              ×{a.occurrence_count}
                            </span>
                          )}
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>
        </div>

        {/* Attacker profiles table */}
        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Attacker profiles</CardTitle>
            <div className="flex items-center gap-1 rounded border border-carbon-600 bg-carbon-800/60 p-1">
              {(["total", "waf", "bot", "last_seen"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setSort(s)}
                  className={cn(
                    "rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest transition-colors",
                    sort === s
                      ? "bg-accent-cyan text-carbon-900"
                      : "text-carbon-200 hover:bg-carbon-700",
                  )}
                >
                  {s === "last_seen" ? "recent" : s}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardBody className="!p-0">
            {attackers.isLoading ? (
              <div className="p-6 text-center text-xs text-carbon-300">Loading…</div>
            ) : (attackers.data?.length ?? 0) === 0 ? (
              <div className="p-6 text-center text-xs text-carbon-300">
                No attacker profiles yet — events flow into this view from WAF + Bot signals.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-carbon-600 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                      <th className="px-4 py-2 font-medium">IP</th>
                      <th className="px-4 py-2 font-medium">Country</th>
                      <th className="px-4 py-2 font-medium">ASN</th>
                      <th className="px-4 py-2 font-medium">WAF block</th>
                      <th className="px-4 py-2 font-medium">WAF mon</th>
                      <th className="px-4 py-2 font-medium">Bot block</th>
                      <th className="px-4 py-2 font-medium">Bot chal</th>
                      <th className="px-4 py-2 font-medium">API 4xx</th>
                      <th className="px-4 py-2 font-medium">Total</th>
                      <th className="px-4 py-2 font-medium">LBs</th>
                      <th className="px-4 py-2 font-medium">Top endpoint</th>
                      <th className="px-4 py-2 font-medium">Last seen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {attackers.data!.map((a) => (
                      <tr
                        key={a.id}
                        className="border-b border-carbon-700/50 hover:bg-carbon-700/40"
                      >
                        <td className="px-4 py-1.5 font-mono text-[11px]">
                          <Link
                            href={`/analytics/security/attackers/${encodeURIComponent(a.source_ip)}`}
                            className="text-accent-cyan hover:underline"
                          >
                            {a.source_ip}
                          </Link>
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] text-carbon-100">
                          {a.source_country ?? "—"}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] text-carbon-300">
                          {a.source_asn ? `AS${a.source_asn}` : "—"}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] tabular-nums text-accent-red">
                          {a.waf_block_count.toLocaleString()}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] tabular-nums text-accent-amber">
                          {a.waf_monitor_count.toLocaleString()}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] tabular-nums text-accent-red">
                          {a.bot_block_count.toLocaleString()}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] tabular-nums text-accent-amber">
                          {a.bot_challenge_count.toLocaleString()}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] tabular-nums text-accent-cyan">
                          {a.api_4xx_count.toLocaleString()}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] font-semibold tabular-nums text-carbon-100">
                          {a.total_events.toLocaleString()}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] tabular-nums text-carbon-100">
                          {a.distinct_lbs}
                        </td>
                        <td
                          className="max-w-xs truncate px-4 py-1.5 font-mono text-[11px] text-carbon-200"
                          title={a.top_endpoint ?? ""}
                        >
                          {a.top_endpoint ?? "—"}
                        </td>
                        <td
                          className="px-4 py-1.5 font-mono text-[10px] text-carbon-300"
                          title={a.last_seen_at ? format(new Date(a.last_seen_at), "PPpp") : ""}
                        >
                          {a.last_seen_at
                            ? formatDistanceToNow(new Date(a.last_seen_at), { addSuffix: true })
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
      </div>
    </Shell>
  );
}
