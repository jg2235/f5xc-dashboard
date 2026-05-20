"use client";

import { format } from "date-fns";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ApiSparklinePoint } from "@/lib/api";

export function ApiEndpointSparkline({
  points,
  height = 200,
}: {
  points: ApiSparklinePoint[];
  height?: number;
}) {
  if (points.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded border border-dashed border-carbon-600 bg-carbon-800/40 font-mono text-[10px] text-carbon-300"
        style={{ height }}
      >
        no metrics for this endpoint yet — wait for the next 5-minute sync cycle
      </div>
    );
  }
  const data = points.map((p) => ({
    label: format(new Date(p.bucket_time), "HH:mm"),
    requests: p.request_count,
    p99: p.latency_p99_ms,
    p95: p.latency_p95_ms,
    p50: p.latency_p50_ms,
    errors: p.error_4xx_count + p.error_5xx_count,
  }));

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
          label={{ value: "ms", angle: 90, position: "insideRight", fill: "#7a8599", fontSize: 9 }}
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
          dataKey="p99"
          stroke="#ff4d6d"
          strokeWidth={1.5}
          dot={false}
          name="p99 latency (ms)"
        />
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="p50"
          stroke="#a78bfa"
          strokeWidth={1.5}
          strokeDasharray="3 3"
          dot={false}
          name="p50 latency (ms)"
        />
        <Tooltip
          contentStyle={{
            background: "#ffffff",
            border: "1px solid #2a3142",
            borderRadius: 6,
            fontSize: 11,
          }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
