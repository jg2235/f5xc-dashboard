"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { format, formatDistanceToNow } from "date-fns";
import { useState } from "react";
import { CheckCircle2, X, RotateCcw } from "lucide-react";
import { api, type AlertOut } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { AlertSeverityBadge, AlertStatusBadge } from "@/components/analytics/AlertBadges";
import { cn } from "@/lib/cn";

type StatusFilter = "all" | "open" | "acknowledged" | "resolved";
type SeverityFilter = "all" | "critical" | "warning" | "info";

export default function AlertsPage() {
  const ready = useRequireAuth();
  const qc = useQueryClient();
  const [status, setStatus] = useState<StatusFilter>("open");
  const [severity, setSeverity] = useState<SeverityFilter>("all");

  const summary = useQuery({
    queryKey: ["alert-summary"],
    queryFn: () => api.alertSummary(),
    enabled: ready,
    refetchInterval: 30_000,
  });
  const alerts = useQuery({
    queryKey: ["alerts-list", status, severity],
    queryFn: () =>
      api.listAlerts({
        status,
        severity,
        limit: 500,
      }),
    enabled: ready,
    refetchInterval: 30_000,
  });

  const ack = useMutation({
    mutationFn: (id: string) => api.acknowledgeAlert(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts-list"] });
      qc.invalidateQueries({ queryKey: ["alert-summary"] });
    },
  });
  const resolve = useMutation({
    mutationFn: (id: string) => api.resolveAlert(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts-list"] });
      qc.invalidateQueries({ queryKey: ["alert-summary"] });
    },
  });
  const reopen = useMutation({
    mutationFn: (id: string) => api.reopenAlert(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts-list"] });
      qc.invalidateQueries({ queryKey: ["alert-summary"] });
    },
  });

  if (!ready) return null;

  return (
    <Shell>
      <div className="px-8 py-8">
        <div className="mb-6">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
            Alerts
          </div>
          <h1 className="font-display text-3xl font-semibold text-carbon-100">
            Alert Inbox
          </h1>
          <div className="mt-1 font-mono text-xs text-carbon-300">
            Rule engine fires every analytics cycle. Alerts dedupe by rule + key.
          </div>
        </div>

        {/* Summary stats */}
        <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard
            label="Open"
            value={summary.data?.open ?? "—"}
            tone={summary.data && summary.data.open > 0 ? "warn" : "ok"}
          />
          <StatCard
            label="Critical (open)"
            value={summary.data?.critical ?? "—"}
            tone={summary.data && summary.data.critical > 0 ? "critical" : "ok"}
          />
          <StatCard
            label="Acknowledged"
            value={summary.data?.acknowledged ?? "—"}
            tone="info"
          />
          <StatCard
            label="Resolved"
            value={summary.data?.resolved ?? "—"}
            tone="ok"
          />
        </div>

        {/* Filters */}
        <Card className="mb-4">
          <CardBody className="flex flex-wrap items-center gap-4">
            <FilterGroup
              label="Status"
              value={status}
              setValue={(v) => setStatus(v as StatusFilter)}
              options={["open", "acknowledged", "resolved", "all"]}
            />
            <FilterGroup
              label="Severity"
              value={severity}
              setValue={(v) => setSeverity(v as SeverityFilter)}
              options={["all", "critical", "warning", "info"]}
            />
          </CardBody>
        </Card>

        {/* Alert list */}
        <Card>
          <CardHeader>
            <CardTitle>
              {alerts.data?.length ?? 0} alert{alerts.data?.length === 1 ? "" : "s"}
            </CardTitle>
          </CardHeader>
          <CardBody className="!p-0">
            {alerts.isLoading ? (
              <div className="p-6 text-center text-xs text-carbon-300">Loading…</div>
            ) : (alerts.data?.length ?? 0) === 0 ? (
              <div className="p-6 text-center text-xs text-accent-green">
                ✓ no alerts match these filters
              </div>
            ) : (
              <ul className="divide-y divide-carbon-700">
                {alerts.data!.map((a) => (
                  <AlertRow
                    key={a.id}
                    alert={a}
                    onAck={() => ack.mutate(a.id)}
                    onResolve={() => resolve.mutate(a.id)}
                    onReopen={() => reopen.mutate(a.id)}
                    busy={ack.isPending || resolve.isPending || reopen.isPending}
                  />
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>
    </Shell>
  );
}

function FilterGroup({
  label,
  value,
  setValue,
  options,
}: {
  label: string;
  value: string;
  setValue: (v: string) => void;
  options: string[];
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
        {label}
      </span>
      <div className="flex items-center gap-1 rounded border border-carbon-600 bg-carbon-800/60 p-1">
        {options.map((o) => (
          <button
            key={o}
            onClick={() => setValue(o)}
            className={cn(
              "rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest transition-colors",
              value === o
                ? "bg-accent-cyan text-carbon-900"
                : "text-carbon-200 hover:bg-carbon-700",
            )}
          >
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}

function AlertRow({
  alert,
  onAck,
  onResolve,
  onReopen,
  busy,
}: {
  alert: AlertOut;
  onAck: () => void;
  onResolve: () => void;
  onReopen: () => void;
  busy: boolean;
}) {
  return (
    <li className="px-4 py-3 hover:bg-carbon-700/30">
      <div className="flex items-start gap-4">
        <div className="flex flex-col gap-1.5 pt-1">
          <AlertSeverityBadge severity={alert.severity} />
          <AlertStatusBadge status={alert.status} />
        </div>
        <div className="min-w-0 flex-1">
          <Link
            href={`/alerts/${alert.id}`}
            className="font-mono text-sm text-carbon-100 hover:text-accent-cyan"
          >
            {alert.title}
          </Link>
          <div className="mt-1 line-clamp-2 font-mono text-[11px] text-carbon-200">
            {alert.description}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-3 font-mono text-[10px] text-carbon-300">
            <span>rule: <span className="text-carbon-200">{alert.rule_id}</span></span>
            <span>key: <span className="text-carbon-200">{alert.dedupe_key}</span></span>
            {alert.occurrence_count > 1 && (
              <span className="text-accent-amber">
                ×{alert.occurrence_count} occurrences
              </span>
            )}
            <span title={format(new Date(alert.first_seen_at), "PPpp")}>
              first {formatDistanceToNow(new Date(alert.first_seen_at), { addSuffix: true })}
            </span>
            <span title={format(new Date(alert.last_seen_at), "PPpp")}>
              last {formatDistanceToNow(new Date(alert.last_seen_at), { addSuffix: true })}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {alert.status === "open" && (
            <>
              <ActionButton
                onClick={onAck}
                disabled={busy}
                icon={<CheckCircle2 size={11} />}
                label="Ack"
                tone="amber"
              />
              <ActionButton
                onClick={onResolve}
                disabled={busy}
                icon={<X size={11} />}
                label="Resolve"
                tone="green"
              />
            </>
          )}
          {alert.status === "acknowledged" && (
            <>
              <ActionButton
                onClick={onResolve}
                disabled={busy}
                icon={<X size={11} />}
                label="Resolve"
                tone="green"
              />
              <ActionButton
                onClick={onReopen}
                disabled={busy}
                icon={<RotateCcw size={11} />}
                label="Reopen"
                tone="cyan"
              />
            </>
          )}
          {alert.status === "resolved" && (
            <ActionButton
              onClick={onReopen}
              disabled={busy}
              icon={<RotateCcw size={11} />}
              label="Reopen"
              tone="cyan"
            />
          )}
        </div>
      </div>
    </li>
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
        "inline-flex items-center gap-1 rounded border px-2 py-1 font-mono text-[10px] uppercase tracking-widest transition-colors disabled:opacity-50",
        toneCls[tone],
      )}
    >
      {icon} {label}
    </button>
  );
}
