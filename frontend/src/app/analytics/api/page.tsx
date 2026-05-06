"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { format, formatDistanceToNow } from "date-fns";
import { useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { api, type ApiTopKDim } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { DiscoveryStateBadge } from "@/components/analytics/DiscoveryStateBadge";
import { WafTopKWidget } from "@/components/analytics/WafTopKWidget";
import { cn } from "@/lib/cn";

type SortOption = "volume" | "last_seen" | "method" | "path";

const TOPK_PANELS: { dim: ApiTopKDim; title: string; tone: "cyan" | "red" | "violet" | "amber" }[] = [
  { dim: "volume", title: "Top endpoints by volume", tone: "cyan" },
  { dim: "latency_p99", title: "Top endpoints by p99 latency", tone: "amber" },
  { dim: "error_rate", title: "Top endpoints by error rate (‰)", tone: "red" },
  { dim: "shadow", title: "Top shadow endpoints by traffic", tone: "violet" },
  { dim: "method", title: "HTTP method distribution", tone: "cyan" },
  { dim: "auth_type", title: "Authentication distribution", tone: "violet" },
];

export default function ApiAnalyticsPage() {
  const ready = useRequireAuth();
  const [hours, setHours] = useState<number>(24);
  const [shadowOnly, setShadowOnly] = useState<boolean>(false);
  const [sort, setSort] = useState<SortOption>("volume");

  const overview = useQuery({
    queryKey: ["api-overview", hours * 60],
    queryFn: () => api.apiOverview(hours * 60),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const discoveryState = useQuery({
    queryKey: ["api-discovery-state"],
    queryFn: () => api.apiDiscoveryState(),
    enabled: ready,
    refetchInterval: 60_000,
  });
  const endpoints = useQuery({
    queryKey: ["api-endpoints-list", shadowOnly, sort],
    queryFn: () => api.apiEndpoints({ limit: 100, shadowOnly, sort }),
    enabled: ready,
  });

  if (!ready) return null;

  return (
    <Shell>
      <div className="px-8 py-8">
        <div className="mb-6 flex items-end justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
              Analytics · API
            </div>
            <h1 className="font-display text-3xl font-semibold text-carbon-100">API Analytics</h1>
            <div className="mt-1 font-mono text-xs text-carbon-300">
              Discovered API surface — F5 Distributed Cloud ML model output combined with declared OpenAPI specs.
            </div>
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

        {/* Hero stats */}
        <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard
            label="Total endpoints"
            value={overview.data?.total_endpoints ?? "—"}
            tone="info"
          />
          <StatCard
            label="Shadow endpoints"
            value={overview.data?.shadow_endpoints ?? "—"}
            tone={
              overview.data && overview.data.shadow_endpoints > 0 ? "warn" : "ok"
            }
          />
          <StatCard
            label="Avg p99 latency"
            value={
              overview.data?.avg_p99_latency_ms !== null && overview.data?.avg_p99_latency_ms !== undefined
                ? `${overview.data.avg_p99_latency_ms} ms`
                : "—"
            }
            tone={
              overview.data && (overview.data.avg_p99_latency_ms ?? 0) > 500 ? "warn" : "ok"
            }
          />
          <StatCard
            label="Error rate"
            value={overview.data ? `${overview.data.error_rate_pct}%` : "—"}
            tone={
              overview.data && overview.data.error_rate_pct > 5 ? "critical" : "ok"
            }
          />
        </div>

        {/* Discovery state per LB */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>ML discovery state by LB</CardTitle>
          </CardHeader>
          <CardBody className="!p-0">
            {discoveryState.isLoading ? (
              <div className="p-6 text-center text-xs text-carbon-300">Loading…</div>
            ) : (discoveryState.data?.length ?? 0) === 0 ? (
              <div className="p-6 text-center text-xs text-carbon-300">
                No discovery state captured yet.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-carbon-600 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                      <th className="px-4 py-2 font-medium">Load balancer</th>
                      <th className="px-4 py-2 font-medium">State</th>
                      <th className="px-4 py-2 font-medium">Endpoints</th>
                      <th className="px-4 py-2 font-medium">Samples</th>
                      <th className="px-4 py-2 font-medium">Last update</th>
                      <th className="px-4 py-2 font-medium">State changed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {discoveryState.data!.map((r) => (
                      <tr
                        key={`${r.lb_namespace}-${r.lb_name}`}
                        className="border-b border-carbon-700/50 hover:bg-carbon-700/40"
                      >
                        <td className="px-4 py-2 font-mono text-xs text-carbon-100">
                          {r.lb_name}
                          <span className="ml-2 text-[10px] text-carbon-300">[{r.lb_namespace}]</span>
                        </td>
                        <td className="px-4 py-2">
                          <DiscoveryStateBadge state={r.state} confidence={r.confidence_score} />
                        </td>
                        <td className="px-4 py-2 font-mono text-xs tabular-nums text-carbon-100">
                          {r.total_endpoints_discovered.toLocaleString()}
                        </td>
                        <td className="px-4 py-2 font-mono text-xs tabular-nums text-carbon-100">
                          {r.total_traffic_samples.toLocaleString()}
                        </td>
                        <td
                          className="px-4 py-2 font-mono text-[10px] text-carbon-300"
                          title={r.last_learning_update ? format(new Date(r.last_learning_update), "PPpp") : ""}
                        >
                          {r.last_learning_update
                            ? formatDistanceToNow(new Date(r.last_learning_update), { addSuffix: true })
                            : "—"}
                        </td>
                        <td
                          className="px-4 py-2 font-mono text-[10px] text-carbon-300"
                          title={r.state_changed_at ? format(new Date(r.state_changed_at), "PPpp") : ""}
                        >
                          {r.state_changed_at
                            ? formatDistanceToNow(new Date(r.state_changed_at), { addSuffix: true })
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

        {/* Top-K grid */}
        <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {TOPK_PANELS.map((p) => (
            <ApiTopKCard key={p.dim} dim={p.dim} title={p.title} tone={p.tone} hours={hours} />
          ))}
        </div>

        {/* Endpoint inventory */}
        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Endpoint inventory</CardTitle>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                <input
                  type="checkbox"
                  checked={shadowOnly}
                  onChange={(e) => setShadowOnly(e.target.checked)}
                  className="h-3 w-3 rounded border-carbon-600 bg-carbon-800"
                />
                Shadow only
              </label>
              <div className="flex items-center gap-1 rounded border border-carbon-600 bg-carbon-800/60 p-1">
                {(["volume", "last_seen", "method", "path"] as const).map((s) => (
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
                    {s.replace("_", " ")}
                  </button>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardBody className="!p-0">
            {endpoints.isLoading ? (
              <div className="p-6 text-center text-xs text-carbon-300">Loading…</div>
            ) : (endpoints.data?.length ?? 0) === 0 ? (
              <div className="p-6 text-center text-xs text-carbon-300">
                No endpoints discovered yet.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-carbon-600 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                      <th className="px-4 py-2 font-medium">Endpoint</th>
                      <th className="px-4 py-2 font-medium">LB</th>
                      <th className="px-4 py-2 font-medium">Status</th>
                      <th className="px-4 py-2 font-medium">Auth</th>
                      <th className="px-4 py-2 font-medium">Conf</th>
                      <th className="px-4 py-2 font-medium">Samples</th>
                      <th className="px-4 py-2 font-medium">Codes</th>
                      <th className="px-4 py-2 font-medium">Last seen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {endpoints.data!.map((e) => (
                      <tr
                        key={e.id}
                        className="border-b border-carbon-700/50 hover:bg-carbon-700/40"
                      >
                        <td className="px-4 py-1.5">
                          <Link
                            href={`/analytics/api/endpoints/${e.id}`}
                            className="font-mono text-xs text-carbon-100 hover:text-accent-cyan"
                          >
                            <span className="mr-2 rounded bg-carbon-700 px-1.5 py-0.5 text-[10px] uppercase">
                              {e.method}
                            </span>
                            {e.endpoint_path}
                          </Link>
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] text-carbon-200">
                          {e.lb_name}
                        </td>
                        <td className="px-4 py-1.5">
                          {e.is_shadow ? (
                            <span className="inline-flex items-center rounded border border-accent-violet/40 bg-accent-violet/10 px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-accent-violet">
                              Shadow
                            </span>
                          ) : (
                            <span className="inline-flex items-center rounded border border-accent-green/30 bg-accent-green/10 px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-accent-green">
                              Declared
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] uppercase text-carbon-200">
                          {e.auth_type ?? "—"}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] tabular-nums text-carbon-100">
                          {e.discovery_confidence !== null ? `${e.discovery_confidence}%` : "—"}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[11px] tabular-nums text-carbon-100">
                          {e.total_request_samples.toLocaleString()}
                        </td>
                        <td className="px-4 py-1.5 font-mono text-[10px] text-carbon-200">
                          {e.response_codes && e.response_codes.length > 0
                            ? e.response_codes.join(", ")
                            : "—"}
                        </td>
                        <td
                          className="px-4 py-1.5 font-mono text-[10px] text-carbon-300"
                          title={e.last_seen_at ? format(new Date(e.last_seen_at), "PPpp") : ""}
                        >
                          {e.last_seen_at
                            ? formatDistanceToNow(new Date(e.last_seen_at), { addSuffix: true })
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

function ApiTopKCard({
  dim,
  title,
  tone,
  hours,
}: {
  dim: ApiTopKDim;
  title: string;
  tone: "cyan" | "red" | "violet" | "amber";
  hours: number;
}) {
  const q = useQuery({
    queryKey: ["api-topk", dim, hours],
    queryFn: () => api.apiTopK({ dim, hours }),
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
