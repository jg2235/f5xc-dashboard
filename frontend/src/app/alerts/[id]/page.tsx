"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { format, formatDistanceToNow } from "date-fns";
import { use } from "react";
import { ChevronLeft, CheckCircle2, X, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { AlertSeverityBadge, AlertStatusBadge } from "@/components/analytics/AlertBadges";
import { cn } from "@/lib/cn";

export default function AlertDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const ready = useRequireAuth();
  const qc = useQueryClient();
  const { id } = use(params);

  const detail = useQuery({
    queryKey: ["alert-detail", id],
    queryFn: () => api.alertDetail(id),
    enabled: ready,
    refetchInterval: 30_000,
  });

  const ack = useMutation({
    mutationFn: () => api.acknowledgeAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-detail", id] }),
  });
  const resolve = useMutation({
    mutationFn: () => api.resolveAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-detail", id] }),
  });
  const reopen = useMutation({
    mutationFn: () => api.reopenAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-detail", id] }),
  });

  if (!ready) return null;
  const a = detail.data;

  return (
    <Shell>
      <div className="px-8 py-8">
        <Link
          href="/alerts"
          className="mb-3 inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-carbon-300 hover:text-accent-cyan"
        >
          <ChevronLeft size={12} /> back to alerts
        </Link>

        {detail.isLoading || !a ? (
          <div className="py-8 text-center text-xs text-carbon-300">Loading…</div>
        ) : (
          <>
            <div className="mb-6 flex items-start justify-between">
              <div className="min-w-0 flex-1">
                <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
                  Alert · {a.rule_id}
                </div>
                <h1 className="font-display text-3xl font-semibold text-carbon-100">
                  {a.title}
                </h1>
                <div className="mt-2 flex items-center gap-2">
                  <AlertSeverityBadge severity={a.severity} />
                  <AlertStatusBadge status={a.status} />
                  {a.occurrence_count > 1 && (
                    <span className="rounded border border-accent-amber/40 bg-accent-amber/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-accent-amber">
                      ×{a.occurrence_count} occurrences
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {a.status === "open" && (
                  <>
                    <ActionButton
                      onClick={() => ack.mutate()}
                      disabled={ack.isPending}
                      icon={<CheckCircle2 size={12} />}
                      label="Acknowledge"
                      tone="amber"
                    />
                    <ActionButton
                      onClick={() => resolve.mutate()}
                      disabled={resolve.isPending}
                      icon={<X size={12} />}
                      label="Resolve"
                      tone="green"
                    />
                  </>
                )}
                {a.status === "acknowledged" && (
                  <>
                    <ActionButton
                      onClick={() => resolve.mutate()}
                      disabled={resolve.isPending}
                      icon={<X size={12} />}
                      label="Resolve"
                      tone="green"
                    />
                    <ActionButton
                      onClick={() => reopen.mutate()}
                      disabled={reopen.isPending}
                      icon={<RotateCcw size={12} />}
                      label="Reopen"
                      tone="cyan"
                    />
                  </>
                )}
                {a.status === "resolved" && (
                  <ActionButton
                    onClick={() => reopen.mutate()}
                    disabled={reopen.isPending}
                    icon={<RotateCcw size={12} />}
                    label="Reopen"
                    tone="cyan"
                  />
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              <Card className="lg:col-span-2">
                <CardHeader>
                  <CardTitle>Description</CardTitle>
                </CardHeader>
                <CardBody>
                  <p className="font-mono text-sm leading-relaxed text-carbon-100">
                    {a.description || "(no description)"}
                  </p>
                </CardBody>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Lifecycle</CardTitle>
                </CardHeader>
                <CardBody className="space-y-2 font-mono text-xs">
                  <Row
                    label="First seen"
                    value={format(new Date(a.first_seen_at), "PPpp")}
                    sub={formatDistanceToNow(new Date(a.first_seen_at), {
                      addSuffix: true,
                    })}
                  />
                  <Row
                    label="Last seen"
                    value={format(new Date(a.last_seen_at), "PPpp")}
                    sub={formatDistanceToNow(new Date(a.last_seen_at), {
                      addSuffix: true,
                    })}
                  />
                  {a.acknowledged_at && (
                    <Row
                      label="Acknowledged"
                      value={format(new Date(a.acknowledged_at), "PPpp")}
                      sub={formatDistanceToNow(new Date(a.acknowledged_at), {
                        addSuffix: true,
                      })}
                    />
                  )}
                  {a.resolved_at && (
                    <Row
                      label="Resolved"
                      value={format(new Date(a.resolved_at), "PPpp")}
                      sub={formatDistanceToNow(new Date(a.resolved_at), {
                        addSuffix: true,
                      })}
                    />
                  )}
                  <Row label="Dedupe key" value={a.dedupe_key} />
                </CardBody>
              </Card>
            </div>

            {/* Context */}
            <Card className="mt-6">
              <CardHeader>
                <CardTitle>Context</CardTitle>
              </CardHeader>
              <CardBody>
                {Object.keys(a.context).length === 0 ? (
                  <div className="font-mono text-xs text-carbon-300">— none —</div>
                ) : (
                  <dl className="grid grid-cols-1 gap-x-6 gap-y-2 font-mono text-xs md:grid-cols-2">
                    {Object.entries(a.context).map(([k, v]) => (
                      <div
                        key={k}
                        className="flex items-baseline justify-between gap-3 border-b border-carbon-700/50 py-1"
                      >
                        <dt className="text-carbon-300">{k}</dt>
                        <dd
                          className="truncate text-carbon-100"
                          title={String(v)}
                        >
                          {renderContextValue(k, v)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                )}
              </CardBody>
            </Card>
          </>
        )}
      </div>
    </Shell>
  );
}

function renderContextValue(key: string, value: unknown): React.ReactNode {
  // For attacker IPs, link directly to the drill-down
  if (key === "source_ip" && typeof value === "string") {
    return (
      <Link
        href={`/analytics/security/attackers/${encodeURIComponent(value)}`}
        className="text-accent-cyan hover:underline"
      >
        {value}
      </Link>
    );
  }
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Row({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-carbon-300">{label}</span>
      <span className="text-right">
        <span className="block text-carbon-100">{value}</span>
        {sub && (
          <span className="block text-[10px] text-carbon-300">{sub}</span>
        )}
      </span>
    </div>
  );
}

function ActionButton({
  onClick,
  disabled,
  icon,
  label,
  tone,
}: {
  onClick: () => void;
  disabled: boolean;
  icon: React.ReactNode;
  label: string;
  tone: "amber" | "green" | "cyan";
}) {
  const toneCls = {
    amber: "border-accent-amber/40 text-accent-amber hover:bg-accent-amber/10",
    green: "border-accent-green/40 text-accent-green hover:bg-accent-green/10",
    cyan: "border-accent-cyan/40 text-accent-cyan hover:bg-accent-cyan/10",
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex items-center gap-1.5 rounded border px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest transition-colors disabled:opacity-50",
        toneCls[tone],
      )}
    >
      {icon} {label}
    </button>
  );
}
