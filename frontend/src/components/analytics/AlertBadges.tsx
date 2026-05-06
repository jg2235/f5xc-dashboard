"use client";

import { cn } from "@/lib/cn";

const SEV_STYLES: Record<string, string> = {
  critical: "border-accent-red/40 bg-accent-red/10 text-accent-red",
  warning: "border-accent-amber/40 bg-accent-amber/10 text-accent-amber",
  info: "border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan",
};

const STATUS_STYLES: Record<string, string> = {
  open: "border-accent-red/40 bg-accent-red/10 text-accent-red",
  acknowledged: "border-accent-amber/40 bg-accent-amber/10 text-accent-amber",
  resolved: "border-accent-green/30 bg-accent-green/10 text-accent-green",
};

export function AlertSeverityBadge({ severity }: { severity: string }) {
  const cls = SEV_STYLES[severity] ?? "border-carbon-600 bg-carbon-700/40 text-carbon-200";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider",
        cls,
      )}
    >
      {severity}
    </span>
  );
}

export function AlertStatusBadge({ status }: { status: string }) {
  const cls = STATUS_STYLES[status] ?? "border-carbon-600 bg-carbon-700/40 text-carbon-200";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider",
        cls,
      )}
    >
      {status}
    </span>
  );
}
