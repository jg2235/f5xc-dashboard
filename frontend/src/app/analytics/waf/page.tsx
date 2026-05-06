"use client";

import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { useState } from "react";
import { api, type TopKDim } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { WafSparkline } from "@/components/analytics/WafSparkline";
import { WafTopKWidget } from "@/components/analytics/WafTopKWidget";
import { cn } from "@/lib/cn";

type ActionFilter = "all" | "BLOCK" | "MONITOR" | "ALLOW";

const TOPK_PANELS: { dim: TopKDim; title: string; tone: "cyan" | "red" | "violet" | "amber" }[] = [
  { dim: "source_ip", title: "Top source IPs", tone: "red" },
  { dim: "source_country", title: "Top source countries", tone: "violet" },
  { dim: "primary_signature", title: "Top signatures", tone: "red" },
  { dim: "url", title: "Top targeted URLs", tone: "amber" },
  { dim: "lb_name", title: "Top LBs by event volume", tone: "cyan" },
  { dim: "action", title: "Action breakdown", tone: "cyan" },
];

export default function WafAnalyticsPage() {
  const ready = useRequireAuth();
  const [hours, setHours] = useState<number>(24);
  const [actionFilter, setActionFilter] = useState<ActionFilter>("all");

  const overview = useQuery({
    queryKey: ["waf-overview", hours * 60],
    queryFn: () => api.wafOverview(hours * 60),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const sparkline = useQuery({
    queryKey: ["waf-sparkline-tenant", hours],
    queryFn: () => api.wafSparkline({ hours }),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const events = useQuery({
    queryKey: ["waf-events", hours, actionFilter],
    queryFn: () =>
      api.wafEvents({
        hours,
        limit: 100,
        action: actionFilter === "all" ? undefined : actionFilter,
      }),
    enabled: ready,
  });

  if (!ready) return null;

  return (
    <Shell>
      <div className="px-8 py-8">
        {/* Header + window picker */}
        <div className="mb-6 flex items-end justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
              Analytics · WAF
            </div>
            <h1 className="font-display text-3xl font-semibold text-carbon-100">
              WAF Analytics
            </h1>
          </div>
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

        {/* Hero stats — Widget 1-4 */}
        <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Requests" value={overview.data?.total_requests ?? "—"} tone="info" />
          <StatCard
            label="Blocked"
            value={overview.data?.total_blocked ?? "—"}
            tone={
              overview.data && overview.data.total_blocked > 0 ? "critical" : "ok"
            }
          />
          <StatCard
            label="Monitored"
            value={overview.data?.total_monitored ?? "—"}
            tone={overview.data && overview.data.total_monitored > 0 ? "warn" : "ok"}
          />
          <StatCard
            label="Block rate"
            value={overview.data ? `${overview.data.block_rate_pct}%` : "—"}
            tone={
              overview.data && overview.data.block_rate_pct > 5 ? "critical" : "ok"
            }
          />
        </div>

        {/* Widget 5 — sparkline */}
        <Card className="mb-6">
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Tenant traffic & violations</CardTitle>
            <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              {hours}h · 5-min buckets
            </span>
          </CardHeader>
          <CardBody>
            {sparkline.isLoading ? (
              <div className="h-48 text-center text-xs text-carbon-300">Loading…</div>
            ) : (
              <WafSparkline points={sparkline.data?.points ?? []} mode="twin" height={240} />
            )}
          </CardBody>
        </Card>

        {/* Widgets 6-11 — Top-K grid */}
        <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {TOPK_PANELS.map((p) => (
            <TopKCard key={p.dim} dim={p.dim} title={p.title} tone={p.tone} hours={hours} />
          ))}
        </div>

        {/* Widget 12 — recent events */}
        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Recent events</CardTitle>
            <div className="flex items-center gap-1 rounded border border-carbon-600 bg-carbon-800/60 p-1">
              {(["all", "BLOCK", "MONITOR", "ALLOW"] as const).map((a) => (
                <button
                  key={a}
                  onClick={() => setActionFilter(a)}
                  className={cn(
                    "rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest transition-colors",
                    actionFilter === a
                      ? "bg-accent-cyan text-carbon-900"
                      : "text-carbon-200 hover:bg-carbon-700",
                  )}
                >
                  {a}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardBody className="!p-0">
            {events.isLoading ? (
              <div className="p-6 text-center text-xs text-carbon-300">Loading…</div>
            ) : (events.data?.length ?? 0) === 0 ? (
              <div className="p-6 text-center text-xs text-carbon-300">
                No events in this window.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-carbon-600 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                      <th className="px-4 py-2 font-medium">Time</th>
                      <th className="px-4 py-2 font-medium">Action</th>
                      <th className="px-4 py-2 font-medium">LB</th>
                      <th className="px-4 py-2 font-medium">Source</th>
                      <th className="px-4 py-2 font-medium">Method</th>
                      <th className="px-4 py-2 font-medium">URL</th>
                      <th className="px-4 py-2 font-medium">Code</th>
                      <th className="px-4 py-2 font-medium">Signature</th>
                      <th className="px-4 py-2 font-medium">Severity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.data!.map((e, idx) => (
                      <tr
                        key={`${e.event_time}-${idx}`}
                        className="border-b border-carbon-700/50 hover:bg-carbon-700/40"
                      >
                        <td className="px-4 py-1.5 font-mono text-[11px] text-carbon-200">
                          {format(new Date(e.event_time), "HH:mm:ss")}
                        </td>
                        <td className="px-4 py-1.5">
                          <ActionPill action={e.action} />
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] text-carbon-100">{e.lb_name}</td>
                        <td className="px-4 py-1.5 font-mono text-[11px] text-carbon-100">
                          {e.source_ip ?? "—"}
                          {e.source_country && (
                            <span className="ml-1 text-carbon-300">[{e.source_country}]</span>
                          )}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] text-carbon-100">
                          {e.method ?? "—"}
                        </td>
                        <td
                          className="max-w-xs truncate px-4 py-1.5 font-mono text-[11px] text-carbon-200"
                          title={e.url ?? ""}
                        >
                          {e.url ?? "—"}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] text-carbon-100">
                          {e.response_code ?? "—"}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] text-accent-red">
                          {e.primary_signature ?? "—"}
                        </td>
                        <td className="px-4 py-1.5">
                          <SeverityPill severity={e.severity} />
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

function TopKCard({
  dim,
  title,
  tone,
  hours,
}: {
  dim: TopKDim;
  title: string;
  tone: "cyan" | "red" | "violet" | "amber";
  hours: number;
}) {
  const q = useQuery({
    queryKey: ["waf-topk", dim, hours],
    queryFn: () => api.wafTopK({ dim, hours }),
    refetchInterval: 60_000,
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardBody>
        {q.isLoading ? (
          <div className="py-3 text-center text-xs text-carbon-300">Loading…</div>
        ) : (
          <WafTopKWidget entries={q.data?.entries ?? []} tone={tone} />
        )}
      </CardBody>
    </Card>
  );
}

function ActionPill({ action }: { action: string }) {
  const cls = {
    BLOCK: "border-accent-red/40 bg-accent-red/10 text-accent-red",
    MONITOR: "border-accent-amber/30 bg-accent-amber/10 text-accent-amber",
    ALLOW: "border-accent-green/30 bg-accent-green/10 text-accent-green",
  }[action] ?? "border-carbon-600 bg-carbon-700/40 text-carbon-200";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider",
        cls,
      )}
    >
      {action}
    </span>
  );
}

function SeverityPill({ severity }: { severity: string | null }) {
  if (!severity) return <span className="font-mono text-[10px] text-carbon-300">—</span>;
  const cls =
    {
      critical: "text-accent-red",
      high: "text-accent-red/80",
      medium: "text-accent-amber",
      low: "text-accent-cyan",
      info: "text-carbon-300",
    }[severity.toLowerCase()] ?? "text-carbon-200";
  return (
    <span className={cn("font-mono text-[10px] uppercase tracking-wider", cls)}>
      {severity}
    </span>
  );
}
