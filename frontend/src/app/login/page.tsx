"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ChevronsRight, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const login = useMutation({
    mutationFn: () => api.login(username, password),
    onSuccess: (data) => {

      router.push("/");
    },
    onError: (e: Error) => setError(e.message || "Login failed"),
  });

  return (
    <div className="bg-grid flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded bg-accent-cyan text-carbon-900">
            <ChevronsRight size={20} strokeWidth={3} />
          </div>
          <div>
            <div className="font-display text-lg font-semibold uppercase tracking-[0.18em] text-carbon-100">
              F5 Distributed Cloud
            </div>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-carbon-200">
              Dashboard &middot; v0.7
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-carbon-600 bg-carbon-800/80 p-6 shadow-2xl">
          <h1 className="mb-1 font-display text-xl font-semibold text-carbon-100">Sign in</h1>
          <p className="mb-5 text-sm text-carbon-300">Enter your dashboard credentials.</p>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              setError(null);
              login.mutate();
            }}
            className="space-y-4"
          >
            <div>
              <label className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                Username
              </label>
              <input
                type="text"
                autoFocus
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full rounded border border-carbon-600 bg-carbon-900/80 px-3 py-2 text-sm text-carbon-100 placeholder-carbon-300 focus:border-accent-cyan focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-carbon-300">
                Password
              </label>
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded border border-carbon-600 bg-carbon-900/80 px-3 py-2 text-sm text-carbon-100 placeholder-carbon-300 focus:border-accent-cyan focus:outline-none"
              />
            </div>

            {error && (
              <div className="rounded border border-accent-red/40 bg-accent-red/10 px-3 py-2 text-xs text-accent-red">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={login.isPending}
              className="flex w-full items-center justify-center gap-2 rounded bg-accent-cyan px-4 py-2 font-medium text-carbon-900 hover:bg-accent-cyan/90 disabled:opacity-50"
            >
              {login.isPending && <Loader2 size={14} className="animate-spin" />}
              Sign in
            </button>
          </form>
        </div>

        <p className="mt-4 text-center font-mono text-[10px] uppercase tracking-widest text-carbon-300">
          Default: admin / changeme &mdash; change after first login
        </p>
      </div>
    </div>
  );
}
