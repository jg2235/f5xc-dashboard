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
      <div className="font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-carbon-300">
        {label}
      </div>
      <div className={cn("mt-2 font-display text-3xl font-semibold tabular-nums", toneClass)}>{value}</div>
      {sub && <div className="mt-1 text-xs text-carbon-300">{sub}</div>}
    </div>
  );
}
