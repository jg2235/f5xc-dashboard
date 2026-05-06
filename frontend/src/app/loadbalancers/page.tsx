"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { ArrowUpRight } from "lucide-react";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { FeatureBadge } from "@/components/ui/Badge";

export default function LoadBalancersPage() {
  const ready = useRequireAuth();
  const { data, isLoading, error } = useQuery({
    queryKey: ["lbs"],
    queryFn: api.listLoadBalancers,
    enabled: ready,
  });

  if (!ready) return null;

  return (
    <Shell>
      <div className="px-8 py-8">
        <div className="mb-6">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
            Configuration · HTTP load balancers
          </div>
          <h1 className="font-display text-3xl font-semibold text-carbon-100">Load Balancers</h1>
        </div>

        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>All LBs</CardTitle>
            <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              {data ? `${data.length} total` : "—"}
            </span>
          </CardHeader>
          <CardBody className="!p-0">
            {isLoading ? (
              <div className="p-6 text-center text-xs text-carbon-300">Loading…</div>
            ) : error ? (
              <div className="p-6 text-center text-xs text-accent-red">Error loading load balancers</div>
            ) : !data || data.length === 0 ? (
              <div className="p-6 text-center text-xs text-carbon-300">
                No load balancers synced yet. Run a sync from the sidebar.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-carbon-600 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                      <th className="px-4 py-3 font-medium">Name</th>
                      <th className="px-4 py-3 font-medium">Namespace</th>
                      <th className="px-4 py-3 font-medium">Domains</th>
                      <th className="px-4 py-3 font-medium">Type</th>
                      <th className="px-4 py-3 font-medium">Advertised</th>
                      <th className="px-4 py-3 font-medium">Policies</th>
                      <th className="px-4 py-3 font-medium">Pools</th>
                      <th className="px-4 py-3 font-medium text-right">Last seen</th>
                      <th className="px-4 py-3 font-medium text-right"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.map((lb) => (
                      <tr
                        key={lb.id}
                        className="border-b border-carbon-700 transition-colors hover:bg-carbon-700/40"
                      >
                        <td className="px-4 py-3 align-top">
                          <div className="font-mono text-sm text-carbon-100">{lb.name}</div>
                          {lb.advertise_mode && (
                            <div className="mt-0.5 font-mono text-[10px] text-carbon-300">
                              {lb.advertise_mode.replace(/_/g, " ")}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 align-top font-mono text-xs text-carbon-200">
                          {lb.namespace}
                        </td>
                        <td className="px-4 py-3 align-top">
                          <div className="flex flex-col gap-0.5 font-mono text-xs text-carbon-100">
                            {lb.domains.map((d) => (
                              <span key={d}>{d}</span>
                            ))}
                          </div>
                        </td>
                        <td className="px-4 py-3 align-top">
                          <span
                            className={`font-mono text-[10px] uppercase ${
                              lb.lb_type === "https" ? "text-accent-green" : "text-accent-amber"
                            }`}
                          >
                            {lb.lb_type}
                          </span>
                        </td>
                        <td className="px-4 py-3 align-top">
                          <div className="flex flex-wrap gap-1">
                            {lb.advertised_sites.length === 0 ? (
                              <span className="font-mono text-[10px] text-carbon-300">—</span>
                            ) : (
                              lb.advertised_sites.slice(0, 3).map((s) => (
                                <span
                                  key={s}
                                  className="rounded border border-carbon-600 bg-carbon-800/50 px-1.5 py-0.5 font-mono text-[9px] text-carbon-100"
                                >
                                  {s === "__all_re__" ? "all RE" : s}
                                </span>
                              ))
                            )}
                            {lb.advertised_sites.length > 3 && (
                              <span className="font-mono text-[9px] text-carbon-300">
                                +{lb.advertised_sites.length - 3}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 align-top">
                          <div className="flex flex-wrap gap-1">
                            <FeatureBadge enabled={lb.has_waf} label="WAF" tone="cyan" />
                            <FeatureBadge enabled={lb.has_service_policy} label="SVC" tone="violet" />
                            <FeatureBadge enabled={lb.has_bot_defense} label="BOT" tone="green" />
                            <FeatureBadge enabled={lb.has_api_protection} label="API" tone="amber" />
                          </div>
                        </td>
                        <td className="px-4 py-3 align-top">
                          <div className="flex flex-col gap-0.5 font-mono text-xs text-carbon-200">
                            {lb.origin_pool_refs.length === 0 ? (
                              <span className="text-carbon-300">—</span>
                            ) : (
                              lb.origin_pool_refs.map((p) => <span key={p}>{p}</span>)
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right align-top font-mono text-xs text-carbon-300">
                          {formatDistanceToNow(new Date(lb.last_seen_at), { addSuffix: true })}
                        </td>
                        <td className="px-4 py-3 text-right align-top">
                          <Link
                            href={`/loadbalancers/${lb.id}`}
                            className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
                          >
                            detail <ArrowUpRight size={11} />
                          </Link>
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
