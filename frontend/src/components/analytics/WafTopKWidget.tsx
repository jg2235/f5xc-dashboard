"use client";

import type { TopKEntry } from "@/lib/api";
import { cn } from "@/lib/cn";

export function WafTopKWidget({
  entries,
  emptyLabel = "no events in window",
  tone = "cyan",
  formatKey,
}: {
  entries: TopKEntry[];
  emptyLabel?: string;
  tone?: "cyan" | "red" | "violet" | "amber";
  formatKey?: (key: string) => React.ReactNode;
}) {
  if (entries.length === 0) {
    return (
      <div className="py-3 text-center font-mono text-[10px] text-carbon-300">{emptyLabel}</div>
    );
  }
  const max = Math.max(...entries.map((e) => e.count));
  const barColor = {
    cyan: "bg-accent-cyan/40",
    red: "bg-accent-red/40",
    violet: "bg-accent-violet/40",
    amber: "bg-accent-amber/40",
  }[tone];

  return (
    <ul className="space-y-1">
      {entries.map((e) => {
        const pct = max > 0 ? Math.round((e.count / max) * 100) : 0;
        return (
          <li key={e.key} className="relative">
            <div
              className={cn("absolute inset-y-0 left-0 rounded-sm", barColor)}
              style={{ width: `${pct}%` }}
            />
            <div className="relative flex items-center justify-between px-2 py-1 font-mono text-xs">
              <span className="truncate text-carbon-100" title={e.key}>
                {formatKey ? formatKey(e.key) : e.key}
              </span>
              <span className="ml-2 tabular-nums text-carbon-100">{e.count.toLocaleString()}</span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
