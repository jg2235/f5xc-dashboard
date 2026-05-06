import { cn } from "@/lib/cn";
import type { CertStatus, OriginStatus } from "@/lib/api";

const CERT_STATUS_STYLES: Record<CertStatus, string> = {
  ok:       "bg-accent-green/15 text-accent-green border border-accent-green/30",
  warn:     "bg-accent-amber/15 text-accent-amber border border-accent-amber/30",
  critical: "bg-accent-red/15   text-accent-red   border border-accent-red/40 pulse-critical",
  expired:  "bg-accent-red/30   text-white        border border-accent-red/60",
  unknown:  "bg-carbon-500/40   text-carbon-200   border border-carbon-500",
};

const CERT_LABEL: Record<CertStatus, string> = {
  ok: "OK",
  warn: "WARN",
  critical: "CRITICAL",
  expired: "EXPIRED",
  unknown: "UNKNOWN",
};

export function CertStatusBadge({ status }: { status: CertStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider",
        CERT_STATUS_STYLES[status],
      )}
    >
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-current" />
      {CERT_LABEL[status]}
    </span>
  );
}

export function FeatureBadge({
  enabled,
  label,
  tone = "cyan",
}: {
  enabled: boolean;
  label: string;
  tone?: "cyan" | "violet" | "green" | "amber";
}) {
  const toneStyles = {
    cyan: "bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30",
    violet: "bg-accent-violet/10 text-accent-violet border-accent-violet/30",
    green: "bg-accent-green/10 text-accent-green border-accent-green/30",
    amber: "bg-accent-amber/10 text-accent-amber border-accent-amber/30",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase tracking-wider",
        enabled ? toneStyles[tone] : "border-carbon-600 bg-carbon-700/50 text-carbon-300/60 line-through",
      )}
    >
      {label}
    </span>
  );
}

const ORIGIN_STATUS_STYLES: Record<OriginStatus, string> = {
  healthy:   "bg-accent-green/15 text-accent-green border border-accent-green/30",
  unhealthy: "bg-accent-red/20   text-accent-red   border border-accent-red/40 pulse-critical",
  warning:   "bg-accent-amber/15 text-accent-amber border border-accent-amber/30",
  info:      "bg-accent-cyan/10  text-accent-cyan  border border-accent-cyan/30",
  unknown:   "bg-carbon-500/40   text-carbon-200   border border-carbon-500",
};

const ORIGIN_STATUS_LABEL: Record<OriginStatus, string> = {
  healthy: "HEALTHY",
  unhealthy: "UNHEALTHY",
  warning: "WARN",
  info: "INFO",
  unknown: "UNKNOWN",
};

export function OriginStatusBadge({
  status,
  rawLabel,
  size = "sm",
}: {
  status: OriginStatus;
  rawLabel?: string;
  size?: "sm" | "xs";
}) {
  const sizeClass = size === "xs"
    ? "px-1.5 py-0 font-mono text-[9px]"
    : "px-2 py-0.5 font-mono text-[10px]";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded font-semibold uppercase tracking-wider",
        sizeClass,
        ORIGIN_STATUS_STYLES[status],
      )}
      title={rawLabel ?? undefined}
    >
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-current" />
      {rawLabel ?? ORIGIN_STATUS_LABEL[status]}
    </span>
  );
}

export function SiteTypeBadge({ siteType }: { siteType: string | null | undefined }) {
  if (!siteType) return <span className="font-mono text-[10px] text-carbon-300">—</span>;
  const map: Record<string, string> = {
    re: "border-accent-cyan/30 text-accent-cyan bg-accent-cyan/10",
    ce: "border-accent-violet/30 text-accent-violet bg-accent-violet/10",
    virtual: "border-accent-amber/30 text-accent-amber bg-accent-amber/10",
    unknown: "border-carbon-500 text-carbon-300 bg-carbon-700/40",
  };
  const cls = map[siteType] ?? map.unknown;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-widest",
        cls,
      )}
    >
      {siteType}
    </span>
  );
}

// ---------------- Slice 3 ----------------

export function SharedScopeBadge({ shared }: { shared: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-widest",
        shared
          ? "border-accent-violet/40 bg-accent-violet/10 text-accent-violet"
          : "border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan",
      )}
      title={shared ? "Tenant-wide shared policy" : "Local namespace policy"}
    >
      {shared ? "shared" : "local"}
    </span>
  );
}

export function EnforcementBadge({ mode }: { mode: "blocking" | "monitoring" | null | undefined }) {
  if (!mode) return <span className="font-mono text-[10px] text-carbon-300">—</span>;
  const isBlocking = mode === "blocking";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider",
        isBlocking
          ? "border-accent-red/40 bg-accent-red/10 text-accent-red"
          : "border-accent-amber/30 bg-accent-amber/10 text-accent-amber",
      )}
    >
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-current" />
      {mode}
    </span>
  );
}

export function ActionBadge({ action }: { action: string | null | undefined }) {
  if (!action) return <span className="font-mono text-[10px] text-carbon-300">—</span>;
  const upper = action.toUpperCase();
  const cls =
    upper === "DENY" || upper === "DENY_LIST"
      ? "border-accent-red/40 bg-accent-red/10 text-accent-red"
      : upper === "ALLOW" || upper === "ALLOW_LIST"
      ? "border-accent-green/30 bg-accent-green/10 text-accent-green"
      : "border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider",
        cls,
      )}
    >
      {upper}
    </span>
  );
}
