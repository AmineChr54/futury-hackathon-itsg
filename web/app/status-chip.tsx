"use client";

import { useEffect, useState } from "react";

type Status = { ok: boolean; model?: string; key_configured?: boolean } | null;

/** Asks the Python pipeline (through the proxy) whether it is up and has an AI key. */
export function StatusChip() {
  const [status, setStatus] = useState<Status | "offline">(null);

  useEffect(() => {
    let alive = true;
    const check = () => fetch("/api/status", { cache: "no-store" })
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then(s => alive && setStatus(s))
      .catch(() => alive && setStatus("offline"));
    check();
    const id = setInterval(check, 15000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  if (status === null) return <span className="chip">Checking pipeline…</span>;
  if (status === "offline") return <span className="chip bad">Pipeline offline</span>;
  return status.key_configured
    ? <span className="chip ok">AI pipeline online · {status.model?.replace(/^vllm\//, "")}</span>
    : <span className="chip warn">Pipeline online · recorded mode (no AI key)</span>;
}
