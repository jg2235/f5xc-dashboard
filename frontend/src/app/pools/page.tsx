"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { ArrowUpRight, ChevronDown, ChevronRight, Radio } from "lucide-react";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { HealthSummary } from "@/components/ui/HealthMatrix";
import {
  PoolReHealthMatrix,
  PoolReHealthInline,
  ReHealthLegend,
} from "@/components/ui/PoolReHealthGrid";

export default function PoolsPage() {
  const ready = useRequireAuth();
  const stats = useQuery({ queryKey: ["pool-stats"], queryFn: api.poolStats, enabled: ready });
  const pools = useQuery({ queryKey: ["pools"], queryFn: api.listPools, enabled: ready });
  const reHealth = useQuery({
    queryKey: ["pool-re-health"],
    queryFn: api.poolReHealth,
    enabled: ready,
    refetchInterval: 60_000,
  });

  // Track which pools have RE health expanded inline in the table
  const [expandedPools, setExpandedPools] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<"matrix" | "inline">("matrix");

  const togglePool = (id: string) =>
    setExpandedPools((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  // Build a quick lookup: pool_id → PoolReHealthRow
  const reHealthByPool = new Map(
    (reHealth.data ?? []).map((r) => [r.pool_id, r]),
  );

  if (!ready) return null;

  return (
    <Shell>
      <div className="px-8 py-8">
        <div className="mb-6">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
            Configuration · origin pools
          </div>
          <h1 className="font-display text-3xl font-semibold text-carbon-100">Origin Pools</h1>
        </div>

        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Total pools" value={stats.data?.total_pools ?? "—"} tone="info" />
          <StatCard label="Total origins" value={stats.data?.total_origins ?? "—"} />
          <StatCard
            label="Pools w/ unhealthy"
            value={stats.data?.pools_with_unhealthy ?? "—"}
            tone={stats.data && stats.data.pools_with_unhealthy > 0 ? "critical" : "ok"}
          />
          <StatCard
            label="Unhealthy origin × site"
            value={stats.data?.unhealthy_cells ?? "—"}
            sub={stats.data ? `${stats.data.warning_cells} warnings` : undefined}
            tone={stats.data && stats.data.unhealthy_cells > 0 ? "critical" : "ok"}
          />
        </div>

        {/* RE health matrix — primary new section */}
        <Card className="mb-6">
          <CardHeader className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Radio size={14} className="text-accent-cyan" strokeWidth={1.75} />
              <CardTitle>Regional Edge health per pool</CardTitle>
            </div>
            <div className="flex items-center gap-4">
              <ReHealthLegend />
              <div className="flex rounded border border-carbon-600 overflow-hidden font-mono text-[10px] uppercase tracking-widest">
                <button
                  onClick={() => setViewMode("matrix")}
                  className={`px-3 py-1.5 transition-colors ${viewMode === "matrix" ? "bg-accent-cyan/20 text-accent-cyan" : "text-carbon-300 hover:bg-carbon-700/40"}`}
                >
                  Matrix
                </button>
                <button
                  onClick={() => setViewMode("inline")}
                  className={`px-3 py-1.5 border-l border-carbon-600 transition-colors ${viewMode === "inline" ? "bg-accent-cyan/20 text-accent-cyan" : "text-carbon-300 hover:bg-carbon-700/40"}`}
                >
                  Inline
                </button>
              </div>
            </div>
          </CardHeader>
          <CardBody>
            {reHealth.isLoading ? (
              <div className="flex h-24 items-center justify-center text-xs text-carbon-300">
                Loading RE health data…
              </div>
            ) : viewMode === "matrix" ? (
              <PoolReHealthMatrix rows={reHealth.data ?? []} />
            ) : (
              <div className="space-y-3">
                {(reHealth.data ?? []).map((row) => (
                  <div key={row.pool_id} className="rounded border border-carbon-600 bg-carbon-800/40 p-3">
                    <div className="mb-2 font-mono text-xs font-medium text-carbon-100">
                      {row.pool_namespace} / {row.pool_name}
                    </div>
                    <PoolReHealthInline row={row} />
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>

        {/* Pool inventory table */}
        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Pool inventory</CardTitle>
            <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              {pools.data ? `${pools.data.length} pools` : "—"}
            </span>
          </CardHeader>
          <CardBody className="!p-0">
            {pools.isLoading ? (
              <div className="p-6 text-center text-xs text-carbon-300">Loading…</div>
            ) : !pools.data || pools.data.length === 0 ? (
              <div className="p-6 text-center text-xs text-carbon-300">
                No pools synced yet. Run a sync from the sidebar.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-carbon-600 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                      <th className="px-4 py-3 font-medium w-6"></th>
                      <th className="px-4 py-3 font-medium">Name</th>
                      <th className="px-4 py-3 font-medium">Namespace</th>
                      <th className="px-4 py-3 font-medium">Port</th>
                      <th className="px-4 py-3 font-medium">Algorithm</th>
                      <th className="px-4 py-3 font-medium">Origins</th>
                      <th className="px-4 py-3 font-medium">Health (origin × site)</th>
                      <th className="px-4 py-3 font-medium text-right">Last probe</th>
                      <th className="px-4 py-3 font-medium text-right"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {pools.data.map((p) => {
                      const total = p.healthy_count + p.unhealthy_count + p.warning_count;
                      const reRow = reHealthByPool.get(p.id as string);
                      const hasRe = reRow && reRow.re_sites.length > 0;
                      const expanded = expandedPools.has(p.id as string);

                      return (
                        <>
                          <tr
                            key={p.id}
                            className="border-b border-carbon-700 transition-colors hover:bg-carbon-700/40"
                          >
                            <td className="px-4 py-3 align-top">
                              {hasRe && (
                                <button
                                  onClick={() => togglePool(p.id as string)}
                                  className="text-carbon-400 hover:text-accent-cyan transition-colors"
                                  title="Toggle RE health"
                                >
                                  {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                                </button>
                              )}
                            </td>
                            <td className="px-4 py-3 align-top font-mono text-sm text-carbon-100">
                              {p.name}
                            </td>
                            <td className="px-4 py-3 align-top font-mono text-xs text-carbon-200">
                              {p.namespace}
                            </td>
                            <td className="px-4 py-3 align-top font-mono text-xs text-carbon-100">
                              {p.port ?? "—"}
                            </td>
                            <td className="px-4 py-3 align-top font-mono text-[10px] text-carbon-200">
                              {p.lb_algorithm ?? "—"}
                            </td>
                            <td className="px-4 py-3 align-top font-mono text-xs text-carbon-100">
                              {p.origin_count}
                            </td>
                            <td className="px-4 py-3 align-top">
                              <HealthSummary
                                healthy={p.healthy_count}
                                unhealthy={p.unhealthy_count}
                                warning={p.warning_count}
                                total={total}
                              />
                            </td>
                            <td className="px-4 py-3 text-right align-top font-mono text-xs text-carbon-300">
                              {p.last_healthcheck_at
                                ? formatDistanceToNow(new Date(p.last_healthcheck_at), { addSuffix: true })
                                : "—"}
                            </td>
                            <td className="px-4 py-3 text-right align-top">
                              <Link
                                href={`/pools/${p.id}`}
                                className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
                              >
                                detail <ArrowUpRight size={11} />
                              </Link>
                            </td>
                          </tr>
                          {/* Inline RE health expansion */}
                          {hasRe && expanded && (
                            <tr key={`${p.id}-re`} className="border-b border-carbon-700 bg-carbon-800/60">
                              <td colSpan={9} className="px-6 py-3">
                                <div className="mb-1 font-mono text-[10px] uppercase tracking-widest text-carbon-400 flex items-center gap-1.5">
                                  <Radio size={10} className="text-accent-cyan" />
                                  Regional Edge health
                                </div>
                                <PoolReHealthInline row={reRow} />
                              </td>
                            </tr>
                          )}
                        </>
                      );
                    })}
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
