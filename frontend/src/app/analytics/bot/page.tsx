"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { format } from "date-fns";
import { useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { api, type BotTopKDim } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { BotSparkline } from "@/components/analytics/BotSparkline";
import { WafTopKWidget } from "@/components/analytics/WafTopKWidget";
import { cn } from "@/lib/cn";

type ActionFilter = "all" | "BLOCK" | "CHALLENGE" | "ALLOW" | "MONITOR";

const TOPK_PANELS: { dim: BotTopKDim; title: string; tone: "cyan" | "red" | "violet" | "amber" }[] = [
  { dim: "source_ip", title: "Top source IPs", tone: "red" },
  { dim: "source_country", title: "Top source countries", tone: "violet" },
  { dim: "ua_family", title: "Top UA families", tone: "cyan" },
  { dim: "endpoint_path", title: "Top targeted endpoints", tone: "amber" },
  { dim: "challenge_result", title: "Challenge outcomes", tone: "violet" },
  { dim: "bot_category", title: "Bot category breakdown", tone: "cyan" },
];

export default function BotAnalyticsPage() {
  const ready = useRequireAuth();
  const [hours, setHours] = useState<number>(24);
  const [actionFilter, setActionFilter] = useState<ActionFilter>("all");

  const overview = useQuery({
    queryKey: ["bot-overview", hours * 60],
    queryFn: () => api.botOverview(hours * 60),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const sparkline = useQuery({
    queryKey: ["bot-sparkline-tenant", hours],
    queryFn: () => api.botSparkline({ hours }),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const events = useQuery({
    queryKey: ["bot-events", hours, actionFilter],
    queryFn: () =>
      api.botEvents({
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
        <div className="mb-6 flex items-end justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
              Analytics · Bot
            </div>
            <h1 className="font-display text-3xl font-semibold text-carbon-100">Bot Analytics</h1>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/analytics/bot/endpoints"
              className="inline-flex items-center gap-1 rounded border border-carbon-600 px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:bg-carbon-700"
            >
              Endpoints view <ArrowUpRight size={11} />
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
          <StatCard label="Requests" value={overview.data?.total_requests ?? "—"} tone="info" />
          <StatCard
            label="Challenges"
            value={overview.data?.total_challenges ?? "—"}
            tone={overview.data && overview.data.total_challenges > 0 ? "warn" : "ok"}
          />
          <StatCard
            label="Blocks"
            value={overview.data?.total_blocks ?? "—"}
            tone={overview.data && overview.data.total_blocks > 0 ? "critical" : "ok"}
          />
          <StatCard
            label="Challenge rate"
            value={overview.data ? `${overview.data.challenge_rate_pct}%` : "—"}
            tone={
              overview.data && overview.data.challenge_rate_pct > 10 ? "warn" : "ok"
            }
          />
        </div>

        {/* Highlights */}
        <div className="mb-6">
          <div className="mb-3 font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
            Highlights
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <BotDonutCard
              dim="bot_category"
              title="Traffic by Category"
              primaryColor="#be185d"
              hours={hours}
            />
            <BotDonutCard
              dim="action"
              title="Traffic by Action"
              primaryColor="#f59e0b"
              hours={hours}
            />
            <BotDonutCard
              dim="lb_name"
              title="Protected Apps"
              primaryColor="#6366f1"
              hours={hours}
            />
            <BotDonutCard
              dim="ua_family"
              title="Top UA Families"
              primaryColor="#06b6d4"
              hours={hours}
            />
          </div>
        </div>

        {/* Sparkline */}
        <Card className="mb-6">
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Tenant bot traffic & interventions</CardTitle>
            <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              {hours}h · 5-min buckets
            </span>
          </CardHeader>
          <CardBody>
            {sparkline.isLoading ? (
              <div className="h-48 text-center text-xs text-carbon-300">Loading…</div>
            ) : (
              <BotSparkline points={sparkline.data?.points ?? []} mode="twin" height={240} />
            )}
          </CardBody>
        </Card>

        {/* Top-K grid */}
        <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {TOPK_PANELS.map((p) => (
            <BotTopKCard key={p.dim} dim={p.dim} title={p.title} tone={p.tone} hours={hours} />
          ))}
        </div>

        {/* Recent events */}
        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Recent bot events</CardTitle>
            <div className="flex items-center gap-1 rounded border border-carbon-600 bg-carbon-800/60 p-1">
              {(["all", "BLOCK", "CHALLENGE", "MONITOR", "ALLOW"] as const).map((a) => (
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
                No bot events in this window.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-carbon-600 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                      <th className="px-4 py-2 font-medium">Time</th>
                      <th className="px-4 py-2 font-medium">Action</th>
                      <th className="px-4 py-2 font-medium">Source</th>
                      <th className="px-4 py-2 font-medium">Category</th>
                      <th className="px-4 py-2 font-medium">Conf</th>
                      <th className="px-4 py-2 font-medium">Challenge</th>
                      <th className="px-4 py-2 font-medium">IP</th>
                      <th className="px-4 py-2 font-medium">UA</th>
                      <th className="px-4 py-2 font-medium">Endpoint</th>
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
                        <td className="px-4 py-1.5">
                          <SourcePill source={e.source} />
                        </td>
                        <td className="px-4 py-1.5">
                          <CategoryPill category={e.bot_category} />
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] text-carbon-100">
                          {e.confidence_score !== null ? `${e.confidence_score}` : "—"}
                          <span className="ml-1 text-[9px] uppercase text-carbon-300">
                            {e.confidence_bucket !== "unknown" ? e.confidence_bucket : ""}
                          </span>
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] text-carbon-100">
                          {e.challenge_result === "not_issued" ? "—" : e.challenge_result}
                          {e.challenge_type && (
                            <span className="ml-1 text-[9px] text-carbon-300">[{e.challenge_type}]</span>
                          )}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] text-carbon-100">
                          {e.source_ip ?? "—"}
                          {e.source_country && (
                            <span className="ml-1 text-carbon-300">[{e.source_country}]</span>
                          )}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] text-carbon-200" title={e.user_agent ?? ""}>
                          {e.ua_family ?? "—"}
                        </td>
                        <td
                          className="max-w-xs truncate px-4 py-1.5 font-mono text-[11px] text-carbon-200"
                          title={e.endpoint_path ?? ""}
                        >
                          {e.method && <span className="mr-1 text-carbon-300">{e.method}</span>}
                          {e.endpoint_path ?? "—"}
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

function BotTopKCard({
  dim,
  title,
  tone,
  hours,
}: {
  dim: BotTopKDim;
  title: string;
  tone: "cyan" | "red" | "violet" | "amber";
  hours: number;
}) {
  const q = useQuery({
    queryKey: ["bot-topk", dim, hours],
    queryFn: () => api.botTopK({ dim, hours }),
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

const DONUT_FALLBACK_COLORS = ["#9aa5b4", "#cbd5e0", "#e2e8f0", "#f0f4f8"];

function BotDonutCard({
  dim,
  title,
  primaryColor,
  hours,
}: {
  dim: BotTopKDim;
  title: string;
  primaryColor: string;
  hours: number;
}) {
  const q = useQuery({
    queryKey: ["bot-topk-donut", dim, hours],
    queryFn: () => api.botTopK({ dim, hours }),
    refetchInterval: 60_000,
  });

  const entries = q.data?.entries ?? [];
  const total = entries.reduce((s, e) => s + e.count, 0);
  const chartData = entries.slice(0, 5).map((e, i) => ({
    name: e.key.replace(/_/g, " "),
    value: e.count,
    fill: i === 0 ? primaryColor : (DONUT_FALLBACK_COLORS[i - 1] ?? "#0f172a"),
  }));
  const empty = chartData.length === 0;

  return (
    <Card>
      <CardBody>
        <div className="mb-0.5 font-mono text-[10px] uppercase tracking-widest text-carbon-300">
          {title}
        </div>
        <div className="mb-0.5 font-mono text-[9px] text-carbon-400">Total Traffic</div>
        <div className="mb-3 font-display text-2xl font-bold text-carbon-100">{total}</div>

        {q.isLoading ? (
          <div className="flex h-36 items-center justify-center text-xs text-carbon-400">
            Loading…
          </div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={130}>
              <PieChart>
                <Pie
                  data={empty ? [{ name: "none", value: 1, fill: "#e8edf2" }] : chartData}
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={60}
                  dataKey="value"
                  strokeWidth={0}
                >
                  {(empty ? [{ fill: "#e8edf2" }] : chartData).map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Pie>
                {!empty && (
                  <Tooltip
                    contentStyle={{
                      background: "#ffffff",
                      border: "1px solid #d1d9e0",
                      borderRadius: "4px",
                      fontSize: "11px",
                      color: "#102a43",
                    }}
                    formatter={(value: number, name: string) => [value, name]}
                  />
                )}
              </PieChart>
            </ResponsiveContainer>

            {!empty && (
              <div className="mt-2 space-y-1 border-t border-carbon-700 pt-2">
                <div className="flex justify-between font-mono text-[9px] uppercase tracking-wider text-carbon-400">
                  <span>Category</span>
                  <span>Total</span>
                </div>
                {chartData.map((e, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 overflow-hidden">
                      <div
                        className="h-2 w-2 shrink-0 rounded-sm"
                        style={{ background: e.fill }}
                      />
                      <span className="truncate font-mono text-[10px] capitalize text-carbon-200">
                        {e.name}
                      </span>
                    </div>
                    <span className="ml-2 shrink-0 font-mono text-[10px] text-carbon-100">
                      {e.value}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </CardBody>
    </Card>
  );
}

function ActionPill({ action }: { action: string }) {
  const cls = {
    BLOCK: "border-accent-red/40 bg-accent-red/10 text-accent-red",
    CHALLENGE: "border-accent-amber/40 bg-accent-amber/10 text-accent-amber",
    MONITOR: "border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan",
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

function SourcePill({ source }: { source: string }) {
  const isAdvanced = source === "bd_advanced";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider",
        isAdvanced
          ? "border-accent-violet/40 bg-accent-violet/10 text-accent-violet"
          : "border-carbon-600 bg-carbon-700/40 text-carbon-200",
      )}
      title={isAdvanced ? "Bot Defense Advanced" : "Bot Defense Standard"}
    >
      {isAdvanced ? "BD-A" : "STD"}
    </span>
  );
}

function CategoryPill({ category }: { category: string }) {
  const cls = {
    bad_bot: "text-accent-red",
    automation: "text-accent-amber",
    scraper: "text-accent-amber",
    data_center: "text-accent-amber",
    suspicious: "text-accent-amber",
    search_engine: "text-accent-cyan",
    good_bot: "text-accent-green",
    human: "text-accent-green",
  }[category] ?? "text-carbon-200";
  return (
    <span className={cn("font-mono text-[10px] uppercase tracking-wider", cls)}>
      {category.replace(/_/g, " ")}
    </span>
  );
}
