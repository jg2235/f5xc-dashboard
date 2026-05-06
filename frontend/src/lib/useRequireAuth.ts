"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { auth } from "./api";

/**
 * Resolves a session via /me at mount time. Returns true once we have a
 * verified user (cookies were valid). Redirects to /login on 401.
 */
export function useRequireAuth() {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    auth.refresh().then((user) => {
      if (cancelled) return;
      if (user) {
        setReady(true);
      } else {
        router.replace("/login");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [router]);

  return ready;
}
