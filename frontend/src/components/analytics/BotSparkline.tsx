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
import type { BotSparklinePoint } from "@/lib/api";

type Mode = "twin" | "compact";

export function BotSparkline({
  points,
  mode = "twin",
  height = 160,
}: {
  points: BotSparklinePoint[];
  mode?: Mode;
  height?: number;
}) {
  if (points.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded border border-dashed border-carbon-600 bg-carbon-800/40 font-mono text-[10px] text-carbon-300"
        style={{ height }}
      >
        no bot metrics yet — wait for the next 5-minute sync cycle
      </div>
    );
  }

  const data = points.map((p) => {
    const t = new Date(p.bucket_time);
    return {
      ts: t.getTime(),
      label: format(t, "HH:mm"),
      requests: p.request_count,
      // For twin chart, "interventions" = challenges + blocks (security signal)
      interventions: p.challenge_count + p.block_count,
      challenges: p.challenge_count,
      blocks: p.block_count,
      allows: p.allow_count,
    };
  });

  if (mode === "compact") {
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
          label={{ value: "interv", angle: 90, position: "insideRight", fill: "#7a8599", fontSize: 9 }}
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
          dataKey="interventions"
          stroke="#ffb547"
          strokeWidth={1.5}
          dot={false}
          name="challenges + blocks"
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
