"use client";

import { format } from "date-fns";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { WafSparklinePoint } from "@/lib/api";

type Mode = "twin" | "compact" | "blocked-only";

export function WafSparkline({
  points,
  mode = "twin",
  height = 160,
}: {
  points: WafSparklinePoint[];
  mode?: Mode;
  height?: number;
}) {
  if (points.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded border border-dashed border-carbon-600 bg-carbon-800/40 font-mono text-[10px] text-carbon-300"
        style={{ height }}
      >
        no metrics yet — wait for the next 5-minute sync cycle
      </div>
    );
  }

  // Recharts wants epoch ms for time axis or labels for category — use labels for stability
  const data = points.map((p) => {
    const t = new Date(p.bucket_time);
    return {
      ts: t.getTime(),
      label: format(t, "HH:mm"),
      requests: p.request_count,
      // For twin chart, blocks include monitored (security signal totals)
      violations: p.blocked_count + p.monitored_count,
      blocked: p.blocked_count,
      monitored: p.monitored_count,
    };
  });

  if (mode === "compact") {
    // No axes, just a single tiny line — used in cards
    return (
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data}>
          <Line
            type="monotone"
            dataKey="requests"
            stroke="#3de3ff"
            strokeWidth={1.5}
            dot={false}
          />
          <Tooltip
            contentStyle={{
              background: "#161b24",
              border: "1px solid #2a3142",
              borderRadius: 6,
              fontSize: 11,
            }}
            labelFormatter={(v) => format(new Date(v), "MMM d HH:mm")}
            formatter={(value: number) => [value.toLocaleString(), "requests"]}
          />
        </LineChart>
      </ResponsiveContainer>
    );
  }

  if (mode === "blocked-only") {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data}>
          <CartesianGrid stroke="#2a3142" strokeDasharray="2 2" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: "#7a8599", fontSize: 10 }}
            interval="preserveStartEnd"
          />
          <YAxis tick={{ fill: "#7a8599", fontSize: 10 }} width={32} />
          <Area
            type="monotone"
            dataKey="blocked"
            stroke="#ff4d6d"
            fill="#ff4d6d"
            fillOpacity={0.25}
          />
          <Tooltip
            contentStyle={{
              background: "#161b24",
              border: "1px solid #2a3142",
              borderRadius: 6,
              fontSize: 11,
            }}
          />
        </AreaChart>
      </ResponsiveContainer>
    );
  }

  // twin mode: requests in cyan, violations in red
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        <CartesianGrid stroke="#2a3142" strokeDasharray="2 2" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: "#7a8599", fontSize: 10 }}
          interval={Math.max(0, Math.floor(data.length / 8) - 1)}
        />
        <YAxis
          yAxisId="left"
          tick={{ fill: "#7a8599", fontSize: 10 }}
          width={32}
          label={{ value: "req/min", angle: -90, position: "insideLeft", fill: "#7a8599", fontSize: 9 }}
        />
        <YAxis
          yAxisId="right"
          orientation="right"
          tick={{ fill: "#7a8599", fontSize: 10 }}
          width={32}
          label={{ value: "viol", angle: 90, position: "insideRight", fill: "#7a8599", fontSize: 9 }}
        />
        <Line
          yAxisId="left"
          type="monotone"
          dataKey="requests"
          stroke="#3de3ff"
          strokeWidth={1.5}
          dot={false}
          name="requests"
        />
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="violations"
          stroke="#ff4d6d"
          strokeWidth={1.5}
          dot={false}
          name="violations"
        />
        <Tooltip
          contentStyle={{
            background: "#161b24",
            border: "1px solid #2a3142",
            borderRadius: 6,
            fontSize: 11,
          }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
