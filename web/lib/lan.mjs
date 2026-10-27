import os from "node:os";

const VIRTUAL = /vEthernet|VirtualBox|VMware|WSL|Hyper-V|docker|Loopback|Tailscale|ZeroTier|utun|bridge/i;

/** The laptop's address on the local network: the first non-internal IPv4, skipping virtual adapters. */
export function lanAddress() {
  const all = Object.entries(os.networkInterfaces()).flatMap(([name, addrs]) =>
    (addrs ?? []).filter(a => a.family === "IPv4" && !a.internal).map(a => ({ name, address: a.address })));
  const real = all.filter(a => !VIRTUAL.test(a.name) && !a.address.startsWith("169.254."));
  // prefer the usual home/venue ranges over anything exotic
  const pick = real.find(a => /^(192\.168|10)\./.test(a.address)) ?? real[0] ?? all[0];
  return pick?.address ?? null;
}

/**
 * The URL judges should open: PUBLIC_URL, else this request's host, with localhost swapped for the LAN IP.
 * @param {string | null} host
 */
export function publicUrl(host) {
  if (process.env.PUBLIC_URL) return process.env.PUBLIC_URL;
  const [name, port] = (host ?? "localhost:3000").split(":");
  const local = name === "localhost" || name.startsWith("127.") || name === "[::1]";
  const lan = local ? lanAddress() : name;
  return `http://${lan ?? name}${port ? `:${port}` : ""}/`;
}
