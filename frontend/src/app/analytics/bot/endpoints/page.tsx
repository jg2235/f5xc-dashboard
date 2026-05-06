"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { ChevronLeft } from "lucide-react";
import { format, formatDistanceToNow } from "date-fns";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/cn";

export default function BotEndpointsPage() {
  const ready = useRequireAuth();
  const [hours, setHours] = useState<number>(24);

  const endpoints = useQuery({
    queryKey: ["bot-endpoints", hours],
    queryFn: () => api.botEndpoints({ hours, limit: 50 }),
    enabled: ready,
    refetchInterval: 60_000,
  });

  if (!ready) return null;

  return (
    <Shell>
      <div className="px-8 py-8">
        <Link
          href="/analytics/bot"
          className="mb-3 inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-carbon-300 hover:text-accent-cyan"
        >
          <ChevronLeft size={12} /> back to bot analytics
        </Link>

        <div className="mb-6 flex items-end justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
              Analytics · Bot · Endpoints
            </div>
            <h1 className="font-display text-3xl font-semibold text-carbon-100">
              Per-endpoint breakdown
            </h1>
            <div className="mt-1 font-mono text-xs text-carbon-300">
              Bot activity grouped by HTTP method + path. Sorted by total event volume.
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

        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Top targeted endpoints</CardTitle>
            <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              {endpoints.data ? `${endpoints.data.length} endpoints` : "—"}
            </span>
          </CardHeader>
          <CardBody className="!p-0">
            {endpoints.isLoading ? (
              <div className="p-6 text-center text-xs text-carbon-300">Loading…</div>
            ) : (endpoints.data?.length ?? 0) === 0 ? (
              <div className="p-6 text-center text-xs text-carbon-300">
                No bot events captured for any endpoint in this window.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-carbon-600 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                      <th className="px-4 py-3 font-medium">Endpoint</th>
                      <th className="px-4 py-3 font-medium">Total</th>
                      <th className="px-4 py-3 font-medium">Block</th>
                      <th className="px-4 py-3 font-medium">Challenge</th>
                      <th className="px-4 py-3 font-medium">Monitor</th>
                      <th className="px-4 py-3 font-medium">Allow</th>
                      <th className="px-4 py-3 font-medium">Distinct IPs</th>
                      <th className="px-4 py-3 font-medium">Top category</th>
                      <th className="px-4 py-3 text-right font-medium">Last seen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {endpoints.data!.map((e, idx) => (
                      <tr
                        key={`${e.endpoint_path}-${e.method ?? "any"}-${idx}`}
                        className="border-b border-carbon-700 hover:bg-carbon-700/40"
                      >
                        <td className="px-4 py-3 align-top">
                          <div className="font-mono text-sm text-carbon-100">
                            {e.method && (
                              <span className="mr-2 rounded bg-carbon-700 px-1.5 py-0.5 text-[10px] uppercase text-carbon-200">
                                {e.method}
                              </span>
                            )}
                            {e.endpoint_path}
                          </div>
                        </td>
                        <td className="px-4 py-3 align-top font-mono text-xs text-carbon-100">
                          {e.total_events.toLocaleString()}
                        </td>
                        <td className="px-4 py-3 align-top font-mono text-xs text-accent-red">
                          {e.block_count.toLocaleString()}
                        </td>
                        <td className="px-4 py-3 align-top font-mono text-xs text-accent-amber">
                          {e.challenge_count.toLocaleString()}
                        </td>
                        <td className="px-4 py-3 align-top font-mono text-xs text-accent-cyan">
                          {e.monitor_count.toLocaleString()}
                        </td>
                        <td className="px-4 py-3 align-top font-mono text-xs text-accent-green">
                          {e.allow_count.toLocaleString()}
                        </td>
                        <td className="px-4 py-3 align-top font-mono text-xs text-carbon-100">
                          {e.distinct_source_ips.toLocaleString()}
                        </td>
                        <td className="px-4 py-3 align-top">
                          {e.top_bot_category ? (
                            <span className="font-mono text-[10px] uppercase tracking-wider text-carbon-200">
                              {e.top_bot_category.replace(/_/g, " ")}
                            </span>
                          ) : (
                            <span className="font-mono text-[10px] text-carbon-300">—</span>
                          )}
                        </td>
                        <td
                          className="px-4 py-3 text-right align-top font-mono text-[10px] text-carbon-300"
                          title={format(new Date(e.last_seen_at), "PPpp")}
                        >
                          {formatDistanceToNow(new Date(e.last_seen_at), { addSuffix: true })}
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
