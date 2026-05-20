import { cn } from "@/lib/cn";

export function StatCard({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: number | string;
  sub?: string;
  tone?: "default" | "ok" | "warn" | "critical" | "info";
}) {
  const toneClass = {
    default: "text-carbon-100 glow-text-cyan",
    ok:       "text-accent-green glow-text-green",
    warn:     "text-accent-amber glow-text-amber",
    critical: "text-accent-red glow-text-red",
    info:     "text-accent-cyan glow-text-cyan",
  }[tone];

  return (
    <div className="rounded-lg border border-carbon-600 bg-carbon-800 p-5 glow-cyan">
      <div className="font-mono text-[11px] font-semibold uppercase tracking-[0.22em] text-carbon-300">
        {label}
      </div>
      <div className={cn("mt-2 font-mono text-4xl font-bold tabular-nums tracking-tight", toneClass)}>{value}</div>
      {sub && <div className="mt-1 text-sm font-medium text-carbon-300">{sub}</div>}
    </div>
  );
}
