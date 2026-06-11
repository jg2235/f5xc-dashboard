"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
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
import { useQuery } from "@tanstack/react-query";
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
  // API analytics is now surfaced per-LB on the Load Balancer detail page
  // (only for LBs with API protection enabled), so it's no longer a nav item.
  { href: "/analytics/security", label: "Security", short: "SEC" },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const policiesActive = pathname.startsWith("/policies");
  const analyticsActive = pathname.startsWith("/analytics");
  const [policiesOpen, setPoliciesOpen] = useState<boolean>(policiesActive);
  const [analyticsOpen, setAnalyticsOpen] = useState<boolean>(analyticsActive);

  // Stepped sync progress, driven by the SSE stream at /sync/all/stream.
  // `done` is the number of completed steps; `total` the step count.
  const [sync, setSync] = useState<{
    active: boolean;
    done: number;
    total: number;
    label: string;
    error: string | null;
  }>({ active: false, done: 0, total: 0, label: "", error: null });
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    // Clean up the stream if the component unmounts mid-sync.
    return () => sourceRef.current?.close();
  }, []);

  const startSync = () => {
    if (sync.active) return;
    setSync({ active: true, done: 0, total: 0, label: "Starting…", error: null });
    const es = new EventSource("/api/v1/sync/all/stream", { withCredentials: true });
    sourceRef.current = es;

    es.onmessage = (ev) => {
      let msg: {
        type: string;
        total?: number;
        index?: number;
        label?: string;
        status?: string;
        error?: string | null;
      };
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.type === "start") {
        setSync((s) => ({ ...s, total: msg.total ?? 0 }));
      } else if (msg.type === "step") {
        setSync((s) => ({ ...s, label: msg.label ?? "", total: msg.total ?? s.total }));
      } else if (msg.type === "progress") {
        setSync((s) => ({
          ...s,
          done: msg.index ?? s.done,
          total: msg.total ?? s.total,
          label: msg.label ?? s.label,
          error: msg.status === "error" ? `${msg.label}: ${msg.error ?? "failed"}` : s.error,
        }));
      } else if (msg.type === "done") {
        es.close();
        sourceRef.current = null;
        // Brief pause so the bar visibly reaches 100% before reload.
        setSync((s) => ({ ...s, active: false, done: s.total, label: "Done" }));
        setTimeout(() => window.location.reload(), 400);
      }
    };

    es.onerror = () => {
      es.close();
      sourceRef.current = null;
      setSync((s) => ({
        ...s,
        active: false,
        error: s.error ?? "Sync connection lost — try again.",
      }));
    };
  };

  const alertSummary = useQuery({
    queryKey: ["alert-summary-sidebar"],
    queryFn: () => api.alertSummary(),
    refetchInterval: 30_000,
  });

  const logout = async () => {
    // v0.7.2 cookie auth: tell the server to revoke + clear cookies before
    // navigating. Best-effort — api.logout() swallows network errors so
    // the SPA always navigates regardless.
    await auth.logout();
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
          onClick={startSync}
          disabled={sync.active}
          className="flex w-full items-center gap-2 rounded border border-carbon-600 bg-carbon-700/50 px-3 py-2 text-xs font-medium text-carbon-100 hover:border-accent-cyan/40 hover:bg-carbon-700 disabled:opacity-50"
        >
          {sync.active ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <RefreshCw size={14} />
          )}
          Sync now
        </button>
        {/* Stepped progress — driven by the /sync/all/stream SSE feed. The bar
            fills as each sync task completes; the label shows the current step. */}
        {(sync.active || sync.done > 0) && (
          <div className="mt-1.5 mb-2">
            <div className="h-1 overflow-hidden rounded-full bg-carbon-700/60">
              <div
                className="h-full rounded-full bg-accent-cyan transition-[width] duration-300 ease-out"
                style={{
                  width: sync.total > 0 ? `${(sync.done / sync.total) * 100}%` : "0%",
                }}
              />
            </div>
            <div className="mt-1 flex items-center justify-between font-mono text-[9px] uppercase tracking-widest text-carbon-300">
              <span className="truncate pr-2">{sync.label}</span>
              {sync.total > 0 && (
                <span className="tabular-nums text-carbon-200">
                  {sync.done}/{sync.total}
                </span>
              )}
            </div>
          </div>
        )}
        {sync.error && (
          <div className="mb-2 px-1 font-mono text-[10px] text-accent-red">
            {sync.error}
          </div>
        )}
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
