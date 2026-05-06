"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { ArrowUpRight } from "lucide-react";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { HealthSummary } from "@/components/ui/HealthMatrix";

export default function PoolsPage() {
  const ready = useRequireAuth();
  const stats = useQuery({ queryKey: ["pool-stats"], queryFn: api.poolStats, enabled: ready });
  const pools = useQuery({ queryKey: ["pools"], queryFn: api.listPools, enabled: ready });

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
            sub={
              stats.data
                ? `${stats.data.warning_cells} warnings`
                : undefined
            }
            tone={stats.data && stats.data.unhealthy_cells > 0 ? "critical" : "ok"}
          />
        </div>

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
                      return (
                        <tr
                          key={p.id}
                          className="border-b border-carbon-700 transition-colors hover:bg-carbon-700/40"
                        >
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
