"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { format } from "date-fns";
import { use } from "react";
import { ChevronLeft } from "lucide-react";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { ApiEndpointSparkline } from "@/components/analytics/ApiEndpointSparkline";

export default function ApiEndpointDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const ready = useRequireAuth();
  const { id } = use(params);

  const detail = useQuery({
    queryKey: ["api-endpoint-detail", id],
    queryFn: () => api.apiEndpointDetail(id),
    enabled: ready,
  });
  const sparkline = useQuery({
    queryKey: ["api-endpoint-sparkline", id, 24],
    queryFn: () => api.apiEndpointSparkline(id, 24),
    enabled: ready,
    refetchInterval: 60_000,
  });

  if (!ready) return null;
  const x = detail.data;

  return (
    <Shell>
      <div className="px-8 py-8">
        <Link
          href="/analytics/api"
          className="mb-3 inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-carbon-300 hover:text-accent-cyan"
        >
          <ChevronLeft size={12} /> back to API analytics
        </Link>

        {detail.isLoading || !x ? (
          <div className="py-8 text-center text-xs text-carbon-300">Loading…</div>
        ) : (
          <>
            <div className="mb-6">
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
                Analytics · API · Endpoint
              </div>
              <h1 className="font-display text-3xl font-semibold text-carbon-100">
                <span className="mr-3 rounded bg-carbon-700 px-2 py-0.5 font-mono text-lg uppercase">
                  {x.method}
                </span>
                {x.endpoint_path}
              </h1>
              <div className="mt-2 flex items-center gap-3 font-mono text-xs text-carbon-300">
                <span>LB: <span className="text-carbon-100">{x.lb_name}</span></span>
                {x.is_shadow ? (
                  <span className="inline-flex items-center rounded border border-accent-violet/40 bg-accent-violet/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-accent-violet">
                    Shadow
                  </span>
                ) : (
                  <span className="inline-flex items-center rounded border border-accent-green/30 bg-accent-green/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-accent-green">
                    Declared in {x.api_definition_name}
                  </span>
                )}
                {x.auth_type && (
                  <span>auth: <span className="text-carbon-100">{x.auth_type}</span></span>
                )}
                {x.discovery_confidence !== null && (
                  <span>confidence: <span className="text-carbon-100">{x.discovery_confidence}%</span></span>
                )}
              </div>
            </div>

            {/* Sparkline */}
            <Card className="mb-6">
              <CardHeader className="flex items-center justify-between">
                <CardTitle>Volume + latency — last 24h</CardTitle>
                <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                  {sparkline.data ? (
                    <>
                      <span className="text-accent-cyan">
                        {sparkline.data.total_requests.toLocaleString()}
                      </span>{" "}
                      req ·{" "}
                      <span className="text-accent-amber">
                        {sparkline.data.total_4xx.toLocaleString()}
                      </span>{" "}
                      4xx ·{" "}
                      <span className="text-accent-red">
                        {sparkline.data.total_5xx.toLocaleString()}
                      </span>{" "}
                      5xx{" "}
                      {sparkline.data.max_p99_ms !== null && (
                        <>
                          · max p99{" "}
                          <span className="text-carbon-100">{sparkline.data.max_p99_ms}ms</span>
                        </>
                      )}
                    </>
                  ) : (
                    "—"
                  )}
                </span>
              </CardHeader>
              <CardBody>
                {sparkline.isLoading ? (
                  <div className="h-[200px] text-center text-xs text-carbon-300">Loading…</div>
                ) : (
                  <ApiEndpointSparkline points={sparkline.data?.points ?? []} height={240} />
                )}
              </CardBody>
            </Card>

            {/* Inferred shape grid */}
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Discovery metadata</CardTitle>
                </CardHeader>
                <CardBody className="space-y-3 font-mono text-xs">
                  <Row label="Total samples" value={x.total_request_samples.toLocaleString()} />
                  <Row
                    label="Discovery confidence"
                    value={x.discovery_confidence !== null ? `${x.discovery_confidence}%` : "—"}
                  />
                  <Row
                    label="First seen"
                    value={x.first_seen_at ? format(new Date(x.first_seen_at), "PPp") : "—"}
                  />
                  <Row
                    label="Last seen"
                    value={x.last_seen_at ? format(new Date(x.last_seen_at), "PPp") : "—"}
                  />
                  <Row
                    label="Response codes observed"
                    value={x.response_codes && x.response_codes.length > 0
                      ? x.response_codes.join(", ")
                      : "—"}
                  />
                </CardBody>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Inferred shape</CardTitle>
                </CardHeader>
                <CardBody className="space-y-4">
                  <ParamSection label="Query parameters" items={x.query_params} />
                  <ParamSection label="Body parameters" items={x.body_params} />
                </CardBody>
              </Card>
            </div>
          </>
        )}
      </div>
    </Shell>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-carbon-300">{label}</span>
      <span className="text-carbon-100">{value}</span>
    </div>
  );
}

function ParamSection({
  label,
  items,
}: {
  label: string;
  items: Array<Record<string, unknown>> | null;
}) {
  return (
    <div>
      <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-carbon-300">
        {label}
      </div>
      {!items || items.length === 0 ? (
        <div className="font-mono text-xs text-carbon-300">— none observed —</div>
      ) : (
        <ul className="space-y-1">
          {items.map((p, i) => (
            <li key={i} className="flex items-baseline gap-3 font-mono text-xs">
              <span className="text-accent-cyan">{String(p.name ?? "?")}</span>
              <span className="text-carbon-300">{String(p.type ?? "any")}</span>
              {p.required ? (
                <span className="rounded border border-accent-red/30 bg-accent-red/10 px-1 text-[9px] uppercase text-accent-red">
                  required
                </span>
              ) : (
                <span className="text-[10px] text-carbon-300">optional</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
