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
    default: "text-carbon-100",
    ok: "text-accent-green",
    warn: "text-accent-amber",
    critical: "text-accent-red",
    info: "text-accent-cyan",
  }[tone];

  return (
    <div className="rounded-lg border border-carbon-600 bg-carbon-800/60 p-5">
      <div className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-carbon-400">
        {label}
      </div>
      <div className={cn("mt-2 font-display text-4xl font-bold tabular-nums", toneClass)}>{value}</div>
      {sub && <div className="mt-1 text-sm font-medium text-carbon-400">{sub}</div>}
    </div>
  );
}
