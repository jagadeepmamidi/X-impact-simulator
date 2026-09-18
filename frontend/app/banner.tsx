"use client";

import { useEffect, useState } from "react";

export const STORAGE_LOSS_COPY =
  "Public demo — runs may be wiped when the free API restarts. Don’t rely on saved history yet.";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export function useEphemeralStorageRisk(): boolean | null {
  const [ephemeral, setEphemeral] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/api/health`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("health unavailable");
        return response.json() as Promise<{
          storage?: { production_ready?: boolean };
        }>;
      })
      .then((payload) => {
        if (!cancelled) setEphemeral(payload.storage?.production_ready !== true);
      })
      .catch(() => {
        if (!cancelled) setEphemeral(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return ephemeral;
}

/** Persistent top warning while health reports non-durable SQLite (e.g. Render /tmp). */
export function EphemeralStorageBanner() {
  const ephemeral = useEphemeralStorageRisk();
  if (ephemeral !== true) return null;
  return (
    <div
      role="status"
      className="sticky top-0 z-50 border-b border-[var(--danger)] bg-[#f8ecec] px-4 py-2 text-center font-[family-name:var(--font-geist-mono)] text-[11px] leading-4 tracking-wide text-[var(--danger)]"
    >
      {STORAGE_LOSS_COPY}
    </div>
  );
}
