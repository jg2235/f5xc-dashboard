"use client";

import { formatDistanceToNow } from "date-fns";
import type { OriginStatus, PoolReHealthRow, ReSiteEntry } from "@/lib/api";
import { cn } from "@/lib/cn";

const STATUS_DOT: Record<OriginStatus, string> = {
  healthy:   "bg-accent-green shadow-[0_0_6px_rgba(57,255,139,0.6)]",
  unhealthy: "bg-accent-red   shadow-[0_0_6px_rgba(255,77,109,0.6)]",
  warning:   "bg-accent-amber shadow-[0_0_6px_rgba(255,181,71,0.5)]",
  info:      "bg-accent-cyan  shadow-[0_0_6px_rgba(61,227,255,0.4)]",
  unknown:   "bg-carbon-400",
};

const STATUS_RING: Record<OriginStatus, string> = {
  healthy:   "border-accent-green/30 bg-accent-green/8",
  unhealthy: "border-accent-red/40   bg-accent-red/10",
  warning:   "border-accent-amber/30 bg-accent-amber/8",
  info:      "border-accent-cyan/20  bg-accent-cyan/6",
  unknown:   "border-carbon-600      bg-carbon-700/30",
};

const STATUS_LABEL: Record<OriginStatus, string> = {
  healthy:   "text-accent-green",
  unhealthy: "text-accent-red",
  warning:   "text-accent-amber",
  info:      "text-accent-cyan",
  unknown:   "text-carbon-400",
};

function ReSiteChip({ site }: { site: ReSiteEntry }) {
  const probe = site.last_probe_at
    ? formatDistanceToNow(new Date(site.last_probe_at), { addSuffix: true })
    : "—";
  const all = site.total_origins;
  const ok = site.healthy_origins;
  const reasons = site.failure_reasons ?? [];
  const reasonStr = reasons.length > 0 ? ` · ${reasons.join(", ")}` : "";

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded border px-2.5 py-1.5 transition-colors",
        STATUS_RING[site.classified_status],
      )}
      title={`${ok}/${all} origins healthy · probed ${probe}${reasonStr}`}
    >
      <span className={cn("h-2 w-2 shrink-0 rounded-full", STATUS_DOT[site.classified_status])} />
      <div className="min-w-0">
        <div className="font-mono text-[11px] font-medium text-carbon-100 truncate">{site.site_name}</div>
        <div className={cn("font-mono text-[9px] uppercase tracking-widest", STATUS_LABEL[site.classified_status])}>
          {ok}/{all} healthy
          {reasons.length > 0 && (
            <span className="ml-1 normal-case tracking-normal text-[9px]">· {reasons[0]}</span>
          )}
        </div>
      </div>
    </div>
  );
}

export function PoolReHealthInline({ row }: { row: PoolReHealthRow }) {
  if (row.re_sites.length === 0) {
    return (
      <span className="font-mono text-[10px] text-carbon-400">no RE data yet</span>
    );
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {row.re_sites.map((site) => (
        <ReSiteChip key={site.site_name} site={site} />
      ))}
    </div>
  );
}

export function PoolReHealthMatrix({ rows }: { rows: PoolReHealthRow[] }) {
  const withData = rows.filter((r) => r.re_sites.length > 0);

  if (withData.length === 0) {
    return (
      <div className="rounded border border-carbon-600 bg-carbon-800/40 p-6 text-center font-mono text-xs text-carbon-300">
        No RE health data yet. Trigger a sync from the sidebar or wait for the next scheduled run.
      </div>
    );
  }

  // Collect all unique RE site names across all pools (for consistent columns)
  const allSites = Array.from(
    new Set(withData.flatMap((r) => r.re_sites.map((s) => s.site_name))),
  ).sort();

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-carbon-600">
            <th className="px-4 py-2 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              Pool
            </th>
            {allSites.map((s) => (
              <th
                key={s}
                className="px-3 py-2 text-center font-mono text-[10px] uppercase tracking-widest text-carbon-300"
              >
                {s}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {withData.map((row) => {
            const siteMap = new Map(row.re_sites.map((s) => [s.site_name, s]));
            return (
              <tr key={row.pool_id} className="border-b border-carbon-700 hover:bg-carbon-700/20 transition-colors">
                <td className="px-4 py-2">
                  <div className="font-mono text-xs font-medium text-carbon-100">{row.pool_name}</div>
                  <div className="font-mono text-[10px] text-carbon-400">{row.pool_namespace}</div>
                </td>
                {allSites.map((siteName) => {
                  const site = siteMap.get(siteName);
                  return (
                    <td key={siteName} className="px-3 py-2 text-center">
                      {site ? (
                        <MatrixCell site={site} />
                      ) : (
                        <span className="inline-block h-3 w-3 rounded-full bg-carbon-600/50" title="No data" />
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MatrixCell({ site }: { site: ReSiteEntry }) {
  const probe = site.last_probe_at
    ? formatDistanceToNow(new Date(site.last_probe_at), { addSuffix: true })
    : "no probe";
  const reasons = site.failure_reasons ?? [];
  const reasonStr = reasons.length > 0 ? ` · ${reasons.join(", ")}` : "";
  return (
    <div
      className="inline-flex flex-col items-center gap-0.5 cursor-default"
      title={`${site.site_name}: ${site.healthy_origins}/${site.total_origins} origins healthy · ${probe}${reasonStr}`}
    >
      <span className={cn("h-3 w-3 rounded-full", STATUS_DOT[site.classified_status])} />
      <span className={cn("font-mono text-[9px]", STATUS_LABEL[site.classified_status])}>
        {site.healthy_origins}/{site.total_origins}
      </span>
    </div>
  );
}

export function ReHealthLegend() {
  const items: Array<{ status: OriginStatus; label: string }> = [
    { status: "healthy",   label: "All healthy" },
    { status: "warning",   label: "Warning" },
    { status: "unhealthy", label: "Unhealthy" },
    { status: "unknown",   label: "No data" },
  ];
  return (
    <div className="flex items-center gap-4 font-mono text-[10px] text-carbon-300">
      {items.map(({ status, label }) => (
        <div key={status} className="flex items-center gap-1.5">
          <span className={cn("h-2 w-2 rounded-full", STATUS_DOT[status])} />
          {label}
        </div>
      ))}
    </div>
  );
}
