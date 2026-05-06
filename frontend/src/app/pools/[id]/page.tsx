"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use } from "react";
import { format, formatDistanceToNow } from "date-fns";
import { ChevronLeft } from "lucide-react";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { HealthMatrix } from "@/components/ui/HealthMatrix";

export default function PoolDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const ready = useRequireAuth();
  const { id } = use(params);
  const pool = useQuery({
    queryKey: ["pool", id],
    queryFn: () => api.getPool(id),
    enabled: ready,
    refetchInterval: 30_000,
  });

  if (!ready) return null;

  if (pool.isLoading) {
    return (
      <Shell>
        <div className="px-8 py-8 text-xs text-carbon-300">Loading…</div>
      </Shell>
    );
  }

  if (pool.error || !pool.data) {
    return (
      <Shell>
        <div className="px-8 py-8 text-xs text-accent-red">Pool not found.</div>
      </Shell>
    );
  }

  const p = pool.data;
  const totalCells = p.healthy_count + p.unhealthy_count + p.warning_count;

  return (
    <Shell>
      <div className="px-8 py-8">
        <Link
          href="/pools"
          className="mb-3 inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-carbon-300 hover:text-accent-cyan"
        >
          <ChevronLeft size={12} /> back to pools
        </Link>
        <div className="mb-6 flex items-end justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
              {p.namespace} · pool
            </div>
            <h1 className="font-display text-3xl font-semibold text-carbon-100">{p.name}</h1>
            <div className="mt-1 font-mono text-xs text-carbon-300">
              {p.lb_algorithm ?? "—"} · port {p.port ?? "—"}
            </div>
          </div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
            {p.last_healthcheck_at
              ? `last health probe ${formatDistanceToNow(new Date(p.last_healthcheck_at), { addSuffix: true })}`
              : "no probes yet"}
          </div>
        </div>

        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-5">
          <StatCard label="Origins" value={p.origin_count} />
          <StatCard label="Sites probed" value={p.site_names.length} />
          <StatCard label="Healthy" value={p.healthy_count} tone="ok" />
          <StatCard label="Warning" value={p.warning_count} tone="warn" />
          <StatCard label="Unhealthy" value={p.unhealthy_count} tone="critical" />
        </div>

        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Origin × Site health</CardTitle>
            <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              {totalCells} cells
            </span>
          </CardHeader>
          <CardBody>
            <HealthMatrix cells={p.health_matrix} />
          </CardBody>
        </Card>

        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Origin servers</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="grid gap-2 md:grid-cols-2">
              {p.origin_addresses.map((a) => (
                <div
                  key={a}
                  className="rounded border border-carbon-600 bg-carbon-800/50 px-3 py-2 font-mono text-xs text-carbon-100"
                >
                  {a}
                </div>
              ))}
            </div>
            {p.healthcheck_refs && p.healthcheck_refs.length > 0 && (
              <div className="mt-4">
                <div className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                  Healthcheck refs
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {p.healthcheck_refs.map((r) => (
                    <span
                      key={r}
                      className="rounded border border-carbon-600 bg-carbon-800/50 px-2 py-0.5 font-mono text-[10px] text-carbon-100"
                    >
                      {r}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </Shell>
  );
}

const _ = format;
