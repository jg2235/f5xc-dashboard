"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use } from "react";
import { format, formatDistanceToNow } from "date-fns";
import { ChevronLeft } from "lucide-react";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Radio } from "lucide-react";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { HealthMatrix } from "@/components/ui/HealthMatrix";
import { PoolReHealthInline } from "@/components/ui/PoolReHealthGrid";
import type { PoolReHealthRow } from "@/lib/api";

export default function PoolDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const ready = useRequireAuth();
  const { id } = use(params);
  const pool = useQuery({
    queryKey: ["pool", id],
    queryFn: () => api.getPool(id),
    enabled: ready,
    refetchInterval: 30_000,
  });
  const reHealth = useQuery({
    queryKey: ["pool-re-health"],
    queryFn: api.poolReHealth,
    enabled: ready,
    refetchInterval: 60_000,
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
  const reRow: PoolReHealthRow | undefined = reHealth.data?.find((r) => r.pool_id === id);

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

        {/* RE health — one chip per RE, prominent summary */}
        {reRow && reRow.re_sites.length > 0 && (
          <Card className="mb-6">
            <CardHeader className="flex items-center gap-2">
              <Radio size={14} className="text-accent-cyan" strokeWidth={1.75} />
              <CardTitle>Regional Edge health</CardTitle>
            </CardHeader>
            <CardBody>
              <PoolReHealthInline row={reRow} />
            </CardBody>
          </Card>
        )}

        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Origin × Site health matrix</CardTitle>
            <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              {totalCells} cells
            </span>
          </CardHeader>
          <CardBody>
            <HealthMatrix cells={p.health_matrix} />
          </CardBody>
        </Card>

        {/* Health checks — assigned object name(s) + parsed configuration.
            Mirrors F5 XC's origin pool → Health Checks panel. */}
        {((p.healthcheck_refs?.length ?? 0) > 0 || p.healthchecks.length > 0) && (
          <Card className="mt-6">
            <CardHeader className="flex items-center justify-between">
              <CardTitle>Health checks</CardTitle>
              <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                {(p.healthcheck_refs?.length ?? p.healthchecks.length)} assigned
              </span>
            </CardHeader>
            <CardBody className="space-y-4">
              {(p.healthcheck_refs ?? p.healthchecks.map((h) => h.name)).map((refName) => {
                const hc = p.healthchecks.find((h) => h.name === refName);
                return (
                  <div
                    key={refName}
                    className="rounded border border-carbon-600 bg-carbon-800/40 p-4"
                  >
                    <div className="mb-3 flex items-center gap-2">
                      <span className="font-mono text-sm text-carbon-100">{refName}</span>
                      {hc && (
                        <>
                          <span className="rounded border border-accent-cyan/40 bg-accent-cyan/10 px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-accent-cyan">
                            {hc.protocol}
                          </span>
                          <span className="font-mono text-[10px] text-carbon-300">
                            [{hc.namespace}]
                          </span>
                        </>
                      )}
                    </div>
                    {!hc ? (
                      <div className="font-mono text-[10px] text-carbon-300">
                        Config not synced yet — it will appear after the next sync cycle.
                      </div>
                    ) : (
                      <div className="grid grid-cols-2 gap-x-6 gap-y-2 md:grid-cols-3">
                        <ConfigItem label="Interval" value={hc.interval_seconds !== null ? `${hc.interval_seconds}s` : "—"} />
                        <ConfigItem label="Timeout" value={hc.timeout_seconds !== null ? `${hc.timeout_seconds}s` : "—"} />
                        <ConfigItem label="Jitter" value={hc.jitter_percent !== null ? `${hc.jitter_percent}%` : "—"} />
                        <ConfigItem label="Healthy threshold" value={hc.healthy_threshold ?? "—"} />
                        <ConfigItem label="Unhealthy threshold" value={hc.unhealthy_threshold ?? "—"} />
                        {hc.protocol !== "tcp" && (
                          <>
                            <ConfigItem label="HTTP/2" value={hc.http_use_http2 === null ? "—" : hc.http_use_http2 ? "yes" : "no"} />
                            <ConfigItem label="Path" value={hc.http_path ?? "—"} />
                            <ConfigItem label="Host header" value={hc.http_host_header ?? "—"} />
                            <ConfigItem
                              label="Expected codes"
                              value={hc.expected_status_codes && hc.expected_status_codes.length > 0
                                ? hc.expected_status_codes.join(", ")
                                : "—"}
                            />
                          </>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </CardBody>
          </Card>
        )}

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
          </CardBody>
        </Card>
      </div>
    </Shell>
  );
}

function ConfigItem({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
        {label}
      </div>
      <div className="mt-0.5 break-all font-mono text-xs text-carbon-100">{value}</div>
    </div>
  );
}

const _ = format;
