"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { api, POLICY_TYPE_LABELS, type PolicyTypeUrl } from "@/lib/api";
import { useRequireAuth } from "@/lib/useRequireAuth";
import { Shell } from "@/components/ui/Shell";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";

const TYPES: { url: PolicyTypeUrl; key: keyof Awaited<ReturnType<typeof api.policyStats>> }[] = [
  { url: "app_firewalls", key: "app_firewall" },
  { url: "service_policies", key: "service_policy" },
  { url: "bot_defense_policies", key: "bot_defense_policy" },
  { url: "api_definitions", key: "api_definition" },
];

export default function PoliciesIndex() {
  const ready = useRequireAuth();
  const stats = useQuery({ queryKey: ["policy-stats"], queryFn: api.policyStats, enabled: ready });

  if (!ready) return null;

  return (
    <Shell>
      <div className="px-8 py-8">
        <div className="mb-6">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-carbon-300">
            Policies
          </div>
          <h1 className="font-display text-3xl font-semibold text-carbon-100">Policy Inventory</h1>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {TYPES.map((t) => {
            const s = stats.data?.[t.key];
            return (
              <Card key={t.url}>
                <CardHeader className="flex items-center justify-between">
                  <CardTitle>{POLICY_TYPE_LABELS[t.url]}</CardTitle>
                  <Link
                    href={`/policies/${t.url}`}
                    className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-accent-cyan hover:underline"
                  >
                    open <ArrowUpRight size={11} />
                  </Link>
                </CardHeader>
                <CardBody>
                  <div className="grid grid-cols-4 gap-3">
                    <Stat label="Total" value={s?.total ?? "—"} />
                    <Stat label="Shared" value={s?.shared ?? "—"} accent="violet" />
                    <Stat label="Local" value={s?.local ?? "—"} accent="cyan" />
                    <Stat
                      label="Unattached"
                      value={s?.unattached ?? "—"}
                      accent={s && s.unattached > 0 ? "amber" : undefined}
                    />
                  </div>
                </CardBody>
              </Card>
            );
          })}
        </div>
      </div>
    </Shell>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | string;
  accent?: "violet" | "cyan" | "amber";
}) {
  const cls = accent === "violet"
    ? "text-accent-violet"
    : accent === "cyan"
    ? "text-accent-cyan"
    : accent === "amber"
    ? "text-accent-amber"
    : "text-carbon-100";
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-widest text-carbon-300">{label}</div>
      <div className={`font-display text-2xl font-semibold tabular-nums ${cls}`}>{value}</div>
    </div>
  );
}
