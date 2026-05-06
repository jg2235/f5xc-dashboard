"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import {
  Activity,
  BarChart3,
  Bell,
  ChevronDown,
  ChevronRight,
  ChevronsRight,
  LayoutDashboard,
  Loader2,
  LogOut,
  RefreshCw,
  Server,
  Shield,
  ShieldCheck,
} from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, auth } from "@/lib/api";
import { cn } from "@/lib/cn";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/loadbalancers", label: "Load Balancers", icon: Activity },
  { href: "/pools", label: "Origin Pools", icon: Server },
  { href: "/certificates", label: "Certificates", icon: ShieldCheck },
];

const POLICY_LINKS = [
  { href: "/policies/app_firewalls", label: "App Firewall (WAF)", short: "WAF" },
  { href: "/policies/service_policies", label: "Service Policy", short: "SVC" },
  { href: "/policies/bot_defense_policies", label: "Bot Defense", short: "BOT" },
  { href: "/policies/api_definitions", label: "API Definitions", short: "API" },
];

const ANALYTICS_LINKS = [
  { href: "/analytics/waf", label: "WAF", short: "WAF" },
  { href: "/analytics/bot", label: "Bot", short: "BOT" },
  { href: "/analytics/api", label: "API", short: "API" },
  { href: "/analytics/security", label: "Security", short: "SEC" },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const policiesActive = pathname.startsWith("/policies");
  const analyticsActive = pathname.startsWith("/analytics");
  const [policiesOpen, setPoliciesOpen] = useState<boolean>(policiesActive);
  const [analyticsOpen, setAnalyticsOpen] = useState<boolean>(analyticsActive);

  const syncMut = useMutation({
    mutationFn: () => api.triggerSyncAll(),
    onSuccess: () => window.location.reload(),
  });

  const alertSummary = useQuery({
    queryKey: ["alert-summary-sidebar"],
    queryFn: () => api.alertSummary(),
    refetchInterval: 30_000,
  });

  const logout = () => {
    auth.clear();
    router.push("/login");
  };

  return (
    <aside className="fixed left-0 top-0 z-10 flex h-screen w-60 flex-col border-r border-carbon-700 bg-carbon-800/80 backdrop-blur">
      <div className="flex items-center gap-2 border-b border-carbon-700 px-4 py-4">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-accent-cyan text-carbon-900">
          <ChevronsRight size={16} strokeWidth={3} />
        </div>
        <span className="font-display text-[11px] font-semibold uppercase leading-tight tracking-[0.14em] text-carbon-100">
          F5 Distributed Cloud
          <span className="block text-[10px] tracking-[0.18em] text-carbon-200">
            Dashboard
          </span>
        </span>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {NAV.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname === item.href || pathname.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "mb-1 flex items-center gap-3 rounded px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-carbon-700 text-accent-cyan"
                  : "text-carbon-200 hover:bg-carbon-700/60 hover:text-carbon-100",
              )}
            >
              <Icon size={16} strokeWidth={1.75} />
              {item.label}
              {active && (
                <span className="ml-auto h-1.5 w-1.5 rounded-full bg-accent-cyan shadow-[0_0_8px_rgba(61,227,255,0.8)]" />
              )}
            </Link>
          );
        })}

        {/* Alerts (slice 7) */}
        {(() => {
          const isActive = pathname === "/alerts" || pathname.startsWith("/alerts/");
          const open = alertSummary.data?.open ?? 0;
          const critical = alertSummary.data?.critical ?? 0;
          return (
            <Link
              href="/alerts"
              className={cn(
                "mb-1 mt-2 flex items-center gap-3 rounded px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-carbon-700 text-accent-cyan"
                  : "text-carbon-200 hover:bg-carbon-700/60 hover:text-carbon-100",
              )}
            >
              <Bell size={16} strokeWidth={1.75} />
              Alerts
              {open > 0 && (
                <span
                  className={cn(
                    "ml-auto inline-flex min-w-[1.25rem] items-center justify-center rounded-full px-1.5 py-0.5 font-mono text-[9px] font-bold tabular-nums",
                    critical > 0
                      ? "bg-accent-red text-carbon-900"
                      : "bg-accent-amber text-carbon-900",
                  )}
                >
                  {open > 99 ? "99+" : open}
                </span>
              )}
            </Link>
          );
        })()}

        {/* Analytics group (slice 4) */}
        <button
          onClick={() => setAnalyticsOpen((v) => !v)}
          className={cn(
            "mb-1 mt-2 flex w-full items-center gap-3 rounded px-3 py-2 text-sm font-medium transition-colors",
            analyticsActive
              ? "bg-carbon-700 text-accent-cyan"
              : "text-carbon-200 hover:bg-carbon-700/60 hover:text-carbon-100",
          )}
        >
          <BarChart3 size={16} strokeWidth={1.75} />
          Analytics
          <span className="ml-auto inline-flex items-center">
            {analyticsOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        </button>
        {analyticsOpen && (
          <div className="ml-3 mb-2 border-l border-carbon-700 pl-2">
            {ANALYTICS_LINKS.map((p) => {
              const isActive = pathname === p.href || pathname.startsWith(`${p.href}/`);
              return (
                <Link
                  key={p.href}
                  href={p.href}
                  className={cn(
                    "mb-0.5 flex items-center justify-between rounded px-3 py-1.5 text-xs font-medium transition-colors",
                    isActive
                      ? "bg-carbon-700/70 text-accent-cyan"
                      : "text-carbon-300 hover:bg-carbon-700/40 hover:text-carbon-100",
                  )}
                >
                  <span>{p.label}</span>
                  <span className="font-mono text-[9px] uppercase tracking-widest text-carbon-300">
                    {p.short}
                  </span>
                </Link>
              );
            })}
          </div>
        )}

        {/* Policies group */}
        <button
          onClick={() => setPoliciesOpen((v) => !v)}
          className={cn(
            "mb-1 flex w-full items-center gap-3 rounded px-3 py-2 text-sm font-medium transition-colors",
            policiesActive
              ? "bg-carbon-700 text-accent-cyan"
              : "text-carbon-200 hover:bg-carbon-700/60 hover:text-carbon-100",
          )}
        >
          <Shield size={16} strokeWidth={1.75} />
          Policies
          <span className="ml-auto inline-flex items-center">
            {policiesOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        </button>
        {policiesOpen && (
          <div className="ml-3 mb-2 border-l border-carbon-700 pl-2">
            {POLICY_LINKS.map((p) => {
              const isActive = pathname === p.href || pathname.startsWith(`${p.href}/`);
              return (
                <Link
                  key={p.href}
                  href={p.href}
                  className={cn(
                    "mb-0.5 flex items-center justify-between rounded px-3 py-1.5 text-xs font-medium transition-colors",
                    isActive
                      ? "bg-carbon-700/70 text-accent-cyan"
                      : "text-carbon-300 hover:bg-carbon-700/40 hover:text-carbon-100",
                  )}
                >
                  <span>{p.label}</span>
                  <span className="font-mono text-[9px] uppercase tracking-widest text-carbon-300">
                    {p.short}
                  </span>
                </Link>
              );
            })}
          </div>
        )}
      </nav>

      <div className="border-t border-carbon-700 p-3">
        <button
          onClick={() => syncMut.mutate()}
          disabled={syncMut.isPending}
          className="mb-2 flex w-full items-center gap-2 rounded border border-carbon-600 bg-carbon-700/50 px-3 py-2 text-xs font-medium text-carbon-100 hover:border-accent-cyan/40 hover:bg-carbon-700 disabled:opacity-50"
        >
          {syncMut.isPending ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <RefreshCw size={14} />
          )}
          Sync now
        </button>
        <button
          onClick={logout}
          className="flex w-full items-center gap-2 rounded px-3 py-2 text-xs font-medium text-carbon-200 hover:text-accent-red"
        >
          <LogOut size={14} />
          Sign out
        </button>
      </div>
    </aside>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-grid min-h-screen">
      <Sidebar />
      <main className="ml-60 min-h-screen">{children}</main>
    </div>
  );
}
