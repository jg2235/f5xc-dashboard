"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { format, formatDistanceToNow } from "date-fns";
import { use, useState } from "react";
import { ChevronLeft, ShieldAlert, Bot, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/cn";

const ACTION_STYLES: Record<string, string> = {
  BLOCK: "border-accent-red/40 bg-accent-red/10 text-accent-red",
  CHALLENGE: "border-accent-amber/40 bg-accent-amber/10 text-accent-amber",
  MONITOR: "border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan",
  ALLOW: "border-accent-green/30 bg-accent-green/10 text-accent-green",
};

export default function AttackerDetailPage({
  params,
}: {
  params: Promise<{ ip: string }>;
}) {
  const ready = useRequireAuth();
  const { ip: rawIp } = use(params);
  const sourceIp = decodeURIComponent(rawIp);
  const [hours, setHours] = useState<number>(24);

  const timeline = useQuery({
    queryKey: ["attacker-timeline", sourceIp, hours],
    queryFn: () => api.securityAttackerTimeline(sourceIp, hours, 500),
    enabled: ready,
    refetchInterval: 60_000,
  });

  // Get attacker profile by listing and filtering — there's no single-IP endpoint
  const profile = useQuery({
    queryKey: ["attacker-profile", sourceIp],
    queryFn: async () => {
      const profiles = await api.securityAttackers({ limit: 500 });
      return profiles.find((p) => p.source_ip === sourceIp) ?? null;
    },
    enabled: ready,
  });

  if (!ready) return null;
  const p = profile.data;

  return (
    <Shell>
      <div className="px-8 py-8">
        <Link
          href="/analytics/security"
          className="mb-3 inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-carbon-300 hover:text-accent-cyan"
        >
          <ChevronLeft size={12} /> back to security analytics
        </Link>

        <div className="mb-6 flex items-end justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
              Analytics · Security · Attacker
            </div>
            <h1 className="font-display text-3xl font-semibold text-carbon-100">
              {sourceIp}
            </h1>
            {p && (
              <div className="mt-2 flex flex-wrap items-center gap-3 font-mono text-xs text-carbon-300">
                {p.source_country && (
                  <span>
                    Country: <span className="text-carbon-100">{p.source_country}</span>
                  </span>
                )}
                {p.source_asn && (
                  <span>
                    ASN: <span className="text-carbon-100">AS{p.source_asn}</span>
                  </span>
                )}
                <span>
                  Distinct LBs touched:{" "}
                  <span className="text-carbon-100">{p.distinct_lbs}</span>
                </span>
                {p.first_seen_at && (
                  <span>
                    First seen:{" "}
                    <span className="text-carbon-100">
                      {formatDistanceToNow(new Date(p.first_seen_at), {
                        addSuffix: true,
                      })}
                    </span>
                  </span>
                )}
              </div>
            )}
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

        {/* Signal breakdown */}
        {p && (
          <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
            <SignalCell label="WAF blocks" count={p.waf_block_count} tone="red" />
            <SignalCell label="WAF monitors" count={p.waf_monitor_count} tone="amber" />
            <SignalCell label="Bot blocks" count={p.bot_block_count} tone="red" />
            <SignalCell label="Bot challenges" count={p.bot_challenge_count} tone="amber" />
            <SignalCell label="API 4xx" count={p.api_4xx_count} tone="cyan" />
          </div>
        )}

        {/* Top context */}
        {p && (p.top_endpoint || p.top_signature) && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>Most-targeted</CardTitle>
            </CardHeader>
            <CardBody className="space-y-2 font-mono text-xs">
              {p.top_endpoint && (
                <div className="flex items-baseline justify-between">
                  <span className="text-carbon-300">Top endpoint</span>
                  <span className="text-carbon-100">{p.top_endpoint}</span>
                </div>
              )}
              {p.top_signature && (
                <div className="flex items-baseline justify-between">
                  <span className="text-carbon-300">Top WAF signature</span>
                  <span className="text-accent-red">{p.top_signature}</span>
                </div>
              )}
            </CardBody>
          </Card>
        )}

        {/* Chronological timeline */}
        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Event timeline</CardTitle>
            <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              {timeline.data?.length ?? 0} events · last {hours}h
            </span>
          </CardHeader>
          <CardBody className="!p-0">
            {timeline.isLoading ? (
              <div className="p-6 text-center text-xs text-carbon-300">Loading…</div>
            ) : (timeline.data?.length ?? 0) === 0 ? (
              <div className="p-6 text-center text-xs text-carbon-300">
                No events in this window.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-carbon-600 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                      <th className="px-4 py-2 font-medium">Time</th>
                      <th className="px-4 py-2 font-medium">Signal</th>
                      <th className="px-4 py-2 font-medium">Action</th>
                      <th className="px-4 py-2 font-medium">LB</th>
                      <th className="px-4 py-2 font-medium">Endpoint</th>
                      <th className="px-4 py-2 font-medium">Classifier</th>
                      <th className="px-4 py-2 font-medium">Code</th>
                    </tr>
                  </thead>
                  <tbody>
                    {timeline.data!.map((e, i) => {
                      const dt = new Date(e.event_time);
                      return (
                        <tr
                          key={i}
                          className="border-b border-carbon-700/50 hover:bg-carbon-700/40"
                        >
                          <td
                            className="px-4 py-1.5 font-mono text-[10px] text-carbon-200"
                            title={format(dt, "PPpp")}
                          >
                            {format(dt, "HH:mm:ss")}
                          </td>
                          <td className="px-4 py-1.5">
                            {e.signal === "waf" ? (
                              <span className="inline-flex items-center gap-1 font-mono text-[10px] text-accent-cyan">
                                <ShieldAlert size={11} /> WAF
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 font-mono text-[10px] text-accent-violet">
                                <Bot size={11} /> Bot
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-1.5">
                            <span
                              className={cn(
                                "inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider",
                                ACTION_STYLES[e.action] ??
                                  "border-carbon-600 bg-carbon-700/40 text-carbon-200",
                              )}
                            >
                              {e.action}
                            </span>
                          </td>
                          <td className="px-4 py-1.5 font-mono text-[11px] text-carbon-200">
                            {e.lb_name ?? "—"}
                          </td>
                          <td
                            className="max-w-xs truncate px-4 py-1.5 font-mono text-[11px] text-carbon-100"
                            title={e.endpoint ?? ""}
                          >
                            {e.method && (
                              <span className="mr-1.5 rounded bg-carbon-700 px-1 py-0.5 text-[9px] uppercase">
                                {e.method}
                              </span>
                            )}
                            {e.endpoint ?? "—"}
                          </td>
                          <td
                            className="max-w-[160px] truncate px-4 py-1.5 font-mono text-[10px] text-carbon-200"
                            title={e.classifier ?? ""}
                          >
                            {e.classifier ?? "—"}
                          </td>
                          <td className="px-4 py-1.5 font-mono text-[10px] tabular-nums text-carbon-200">
                            {e.rsp_code ?? "—"}
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

function SignalCell({
  label,
  count,
  tone,
}: {
  label: string;
  count: number;
  tone: "red" | "amber" | "cyan";
}) {
  const colorMap = {
    red: "text-accent-red",
    amber: "text-accent-amber",
    cyan: "text-accent-cyan",
  };
  return (
    <div className="rounded border border-carbon-600 bg-carbon-800/60 p-3">
      <div className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
        {label}
      </div>
      <div
        className={cn(
          "mt-1 font-display text-2xl font-semibold tabular-nums",
          count > 0 ? colorMap[tone] : "text-carbon-300",
        )}
      >
        {count.toLocaleString()}
      </div>
    </div>
  );
}
