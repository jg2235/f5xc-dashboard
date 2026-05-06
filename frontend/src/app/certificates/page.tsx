"use client";

import { useQuery } from "@tanstack/react-query";
import { format, formatDistanceToNow } from "date-fns";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { CertStatusBadge } from "@/components/ui/Badge";

export default function CertificatesPage() {
  const ready = useRequireAuth();
  const stats = useQuery({ queryKey: ["cert-stats"], queryFn: api.certStats, enabled: ready });
  const certs = useQuery({ queryKey: ["certs"], queryFn: () => api.listCertificates(), enabled: ready });

  if (!ready) return null;

  return (
    <Shell>
      <div className="px-8 py-8">
        <div className="mb-6">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
            Configuration · certificate chains
          </div>
          <h1 className="font-display text-3xl font-semibold text-carbon-100">Certificates</h1>
        </div>

        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-5">
          <StatCard label="Total" value={stats.data?.total ?? "—"} tone="info" />
          <StatCard label="OK" value={stats.data?.ok ?? "—"} tone="ok" />
          <StatCard label="Warn (≤30d)" value={stats.data?.warn ?? "—"} tone="warn" />
          <StatCard label="Critical (≤7d)" value={stats.data?.critical ?? "—"} tone="critical" />
          <StatCard label="Expired" value={stats.data?.expired ?? "—"} tone="critical" />
        </div>

        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Certificate inventory</CardTitle>
            <span className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">
              sorted by soonest expiry
            </span>
          </CardHeader>
          <CardBody className="!p-0">
            {certs.isLoading ? (
              <div className="p-6 text-center text-xs text-carbon-300">Loading…</div>
            ) : !certs.data || certs.data.length === 0 ? (
              <div className="p-6 text-center text-xs text-carbon-300">No certificates synced yet.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-carbon-600 text-left font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                      <th className="px-4 py-3 font-medium">Status</th>
                      <th className="px-4 py-3 font-medium">Name</th>
                      <th className="px-4 py-3 font-medium">Subject</th>
                      <th className="px-4 py-3 font-medium">SANs</th>
                      <th className="px-4 py-3 font-medium">Type</th>
                      <th className="px-4 py-3 font-medium">Expires</th>
                      <th className="px-4 py-3 text-right font-medium">Days left</th>
                    </tr>
                  </thead>
                  <tbody>
                    {certs.data.map((c) => (
                      <tr
                        key={c.id}
                        className="border-b border-carbon-700 transition-colors hover:bg-carbon-700/40"
                      >
                        <td className="px-4 py-3 align-top">
                          <CertStatusBadge status={c.status} />
                        </td>
                        <td className="px-4 py-3 align-top">
                          <div className="font-mono text-sm text-carbon-100">{c.name}</div>
                          <div className="font-mono text-[10px] text-carbon-300">{c.namespace}</div>
                        </td>
                        <td className="px-4 py-3 align-top font-mono text-xs text-carbon-100">
                          {c.subject ?? "—"}
                        </td>
                        <td className="px-4 py-3 align-top">
                          <div className="flex flex-col gap-0.5 font-mono text-xs text-carbon-200">
                            {c.san_dns.length === 0 ? (
                              <span className="text-carbon-300">—</span>
                            ) : (
                              c.san_dns.slice(0, 3).map((s) => <span key={s}>{s}</span>)
                            )}
                            {c.san_dns.length > 3 && (
                              <span className="text-carbon-300">+{c.san_dns.length - 3} more</span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 align-top font-mono text-[10px] uppercase text-carbon-200">
                          {c.auto_cert ? "auto" : "manual"}
                        </td>
                        <td className="px-4 py-3 align-top font-mono text-xs text-carbon-100">
                          {c.not_after ? (
                            <>
                              <div>{format(new Date(c.not_after), "yyyy-MM-dd")}</div>
                              <div className="text-[10px] text-carbon-300">
                                {formatDistanceToNow(new Date(c.not_after), { addSuffix: true })}
                              </div>
                            </>
                          ) : (
                            <span className="text-carbon-300">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right align-top">
                          <span
                            className={`font-display text-lg tabular-nums ${
                              c.status === "expired" || c.status === "critical"
                                ? "text-accent-red"
                                : c.status === "warn"
                                ? "text-accent-amber"
                                : "text-carbon-100"
                            }`}
                          >
                            {c.days_until_expiry ?? "—"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </Shell>
  );
}
