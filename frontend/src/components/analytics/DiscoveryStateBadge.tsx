"use client";

import { cn } from "@/lib/cn";

const STATE_STYLES: Record<string, string> = {
  enforcing: "border-accent-green/40 bg-accent-green/10 text-accent-green",
  mature: "border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan",
  learning: "border-accent-amber/40 bg-accent-amber/10 text-accent-amber",
  disabled: "border-carbon-600 bg-carbon-700/40 text-carbon-300",
  unknown: "border-carbon-600 bg-carbon-700/40 text-carbon-300",
};

export function DiscoveryStateBadge({
  state,
  confidence,
}: {
  state: string;
  confidence?: number | null;
}) {
  const cls = STATE_STYLES[state] ?? STATE_STYLES.unknown;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider",
        cls,
      )}
    >
      {state}
      {confidence !== null && confidence !== undefined && (
        <span className="opacity-70">{confidence}%</span>
      )}
    </span>
  );
}
