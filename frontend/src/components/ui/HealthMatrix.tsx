"use client";

import { format, formatDistanceToNow } from "date-fns";
import type { OriginHealthCell, OriginStatus } from "@/lib/api";
import { OriginStatusBadge, SiteTypeBadge } from "./Badge";
import { cn } from "@/lib/cn";

const STATUS_BG: Record<OriginStatus, string> = {
  healthy:   "bg-accent-green/15 hover:bg-accent-green/25",
  unhealthy: "bg-accent-red/20   hover:bg-accent-red/30 ring-1 ring-accent-red/40",
  warning:   "bg-accent-amber/15 hover:bg-accent-amber/25",
  info:      "bg-accent-cyan/10  hover:bg-accent-cyan/20",
  unknown:   "bg-carbon-700/40   hover:bg-carbon-600/40",
};

const STATUS_DOT: Record<OriginStatus, string> = {
  healthy: "bg-accent-green",
  unhealthy: "bg-accent-red",
  warning: "bg-accent-amber",
  info: "bg-accent-cyan",
  unknown: "bg-carbon-300",
};

export function HealthMatrix({ cells }: { cells: OriginHealthCell[] }) {
  if (cells.length === 0) {
    return (
      <div className="rounded border border-carbon-600 bg-carbon-800/40 p-6 text-center font-mono text-xs text-carbon-300">
        No healthcheck data yet. Wait for the next sync cycle, or trigger one from the sidebar.
      </div>
    );
  }

  // Build origin × site grid
  const origins = Array.from(
    new Map(
      cells.map((c) => [
        `${c.origin_address}:${c.origin_port ?? ""}`,
        { address: c.origin_address, port: c.origin_port },
      ]),
    ).values(),
  );
  const sites = Array.from(
    new Map(cells.map((c) => [c.site_name, { name: c.site_name, type: c.site_type }])).values(),
  );

  const cellMap = new Map<string, OriginHealthCell>();
  for (const c of cells) {
    cellMap.set(`${c.origin_address}:${c.origin_port ?? ""}__${c.site_name}`, c);
  }

  const total = origins.length * sites.length;
  const useGroupedList = total > 24;

  if (useGroupedList) {
    return <GroupedList cells={cells} />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="border-collapse">
        <thead>
          <tr>
            <th className="border-b border-carbon-600 px-3 py-2 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              Origin
            </th>
            {sites.map((s) => (
              <th
                key={s.name}
                className="border-b border-carbon-600 px-3 py-2 text-left align-bottom font-mono text-[10px] uppercase tracking-widest text-carbon-300"
              >
                <div className="flex flex-col gap-1">
                  <span>{s.name}</span>
                  <SiteTypeBadge siteType={s.type} />
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {origins.map((o) => (
            <tr key={`${o.address}:${o.port ?? ""}`} className="border-b border-carbon-700">
              <td className="px-3 py-2 align-top">
                <div className="font-mono text-xs text-carbon-100">{o.address}</div>
                {o.port !== null && (
                  <div className="font-mono text-[10px] text-carbon-300">:{o.port}</div>
                )}
              </td>
              {sites.map((s) => {
                const cell = cellMap.get(`${o.address}:${o.port ?? ""}__${s.name}`);
                return (
                  <td key={s.name} className="px-2 py-2 align-top">
                    {cell ? (
                      <CellTile cell={cell} />
                    ) : (
                      <div className="rounded border border-dashed border-carbon-600 bg-carbon-800/40 px-2 py-2 font-mono text-[10px] text-carbon-300">
                        no probe
                      </div>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CellTile({ cell }: { cell: OriginHealthCell }) {
  const change = cell.last_status_change
    ? formatDistanceToNow(new Date(cell.last_status_change), { addSuffix: true })
    : "—";
  const probe = cell.last_probe_at
    ? formatDistanceToNow(new Date(cell.last_probe_at), { addSuffix: true })
    : "—";
  return (
    <div
      className={cn(
        "min-w-[140px] cursor-default rounded px-2 py-1.5 transition-colors",
        STATUS_BG[cell.classified_status],
      )}
      title={`Raw: ${cell.raw_status}\nLast change: ${change}\nLast probe: ${probe}\nFailures: ${cell.consecutive_failures}`}
    >
      <div className="flex items-center justify-between">
        <span
          className={cn(
            "font-mono text-[10px] font-semibold uppercase tracking-wider",
            cell.classified_status === "unhealthy" ? "text-accent-red" :
            cell.classified_status === "warning"   ? "text-accent-amber" :
            cell.classified_status === "info"      ? "text-accent-cyan" :
            cell.classified_status === "healthy"   ? "text-accent-green" :
            "text-carbon-200",
          )}
        >
          {cell.raw_status}
        </span>
        <span className={cn("h-1.5 w-1.5 rounded-full", STATUS_DOT[cell.classified_status])} />
      </div>
      {cell.consecutive_failures > 0 && (
        <div className="mt-1 font-mono text-[9px] text-accent-red/80">
          {cell.consecutive_failures} fails
        </div>
      )}
      <div className="mt-0.5 font-mono text-[9px] text-carbon-300">{probe}</div>
    </div>
  );
}

function GroupedList({ cells }: { cells: OriginHealthCell[] }) {
  // Group by origin
  const groups = new Map<string, OriginHealthCell[]>();
  for (const c of cells) {
    const key = `${c.origin_address}:${c.origin_port ?? ""}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(c);
  }

  return (
    <div className="space-y-3">
      {Array.from(groups.entries()).map(([key, group]) => {
        const counts = group.reduce(
          (acc, c) => {
            acc[c.classified_status] = (acc[c.classified_status] ?? 0) + 1;
            return acc;
          },
          {} as Record<string, number>,
        );
        const total = group.length;
        const healthy = counts.healthy ?? 0;
        return (
          <div key={key} className="rounded border border-carbon-600 bg-carbon-800/40 p-3">
            <div className="mb-2 flex items-baseline justify-between">
              <div className="font-mono text-sm text-carbon-100">{key}</div>
              <div className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                {healthy}/{total} healthy
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {group.map((c) => (
                <div
                  key={c.site_name}
                  className={cn("rounded px-2 py-1", STATUS_BG[c.classified_status])}
                  title={`Raw: ${c.raw_status}`}
                >
                  <div className="flex items-center gap-2">
                    <SiteTypeBadge siteType={c.site_type} />
                    <span className="font-mono text-xs text-carbon-100">{c.site_name}</span>
                    <OriginStatusBadge status={c.classified_status} rawLabel={c.raw_status} size="xs" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function HealthSummary({
  healthy,
  unhealthy,
  warning,
  total,
}: {
  healthy: number;
  unhealthy: number;
  warning: number;
  total: number;
}) {
  if (total === 0) {
    return <span className="font-mono text-[10px] text-carbon-300">no probes yet</span>;
  }
  return (
    <div className="flex items-center gap-2 font-mono text-[10px]">
      <span className="text-accent-green">{healthy} ✓</span>
      {warning > 0 && <span className="text-accent-amber">{warning} ⚠</span>}
      {unhealthy > 0 && <span className="text-accent-red">{unhealthy} ✗</span>}
      <span className="text-carbon-300">/ {total}</span>
    </div>
  );
}

// silence unused var warnings
const _ = format;
