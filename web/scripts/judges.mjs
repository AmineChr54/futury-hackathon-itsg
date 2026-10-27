// One command for the judges' setup: the Python pipeline on localhost, the Next.js portal on the LAN.
//
//   npm run judges              # portal on http://<LAN-IP>:3000, prints a QR code in the terminal
//   PORT=8080 npm run judges    # another port
//   KEEP_PASSWORD=1 npm run judges   # keep PIPELINE_PASSWORD from pipeline/.env (default: open, no sign-in password)
import { spawn } from "node:child_process";
import { copyFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import QRCode from "qrcode";
import { lanAddress } from "../lib/lan.mjs";

const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = path.resolve(WEB, "..");
const PORT = process.env.PORT || "3000";
const NEXT = path.join(WEB, "node_modules", "next", "dist", "bin", "next");
const win = process.platform === "win32";

// pipeline/.env holds the hessian.AI key; start.cmd/start.sh create it the same way
const env = path.join(ROOT, "pipeline", ".env");
if (!existsSync(env)) {
  copyFileSync(path.join(ROOT, "pipeline", ".env.example"), env);
  console.log("created pipeline/.env from .env.example: put the team key after HAI_API_KEY= for the live AI");
}

const children = [];
const run = (cmd, args, opts = {}) => {
  const p = spawn(cmd, args, { stdio: "inherit", ...opts });
  children.push(p);
  return p;
};
const stopAll = code => { children.forEach(c => c.exitCode === null && c.kill()); process.exit(code); };
process.on("SIGINT", () => stopAll(0));
process.on("SIGTERM", () => stopAll(0));

// Python stays on 127.0.0.1; judges only reach it through the portal's proxy
const pyEnv = { ...process.env, PYTHONUNBUFFERED: "1" };
if (!process.env.KEEP_PASSWORD) Object.assign(pyEnv, { PIPELINE_PASSWORD: "", PIPELINE_PASSWORD_ISTG: "", PIPELINE_PASSWORD_DEV: "" });
const py = run(win ? "python" : "python3", [path.join(ROOT, "pipeline", "server.py"), "--host", "127.0.0.1", "--port", "8787"], { cwd: ROOT, env: pyEnv });
py.on("exit", code => { console.error(`pipeline server stopped (${code}); is Python 3.10+ installed and pypdf available? (pip install -r pipeline/requirements.txt)`); stopAll(1); });

const next = args => new Promise((resolve, reject) => {
  const p = run(process.execPath, [NEXT, ...args], { cwd: WEB });
  p.on("exit", code => (code === 0 ? resolve() : reject(new Error(`next ${args[0]} exited with ${code}`))));
});

if (!existsSync(path.join(WEB, ".next", "BUILD_ID"))) await next(["build"]);
const url = `http://${lanAddress() ?? "localhost"}:${PORT}/`;
run(process.execPath, [NEXT, "start", "-H", "0.0.0.0", "-p", PORT], { cwd: WEB }).on("exit", code => stopAll(code ?? 0));

console.log(`\n  §pecs for the judges\n  ${url}\n`);
console.log(await QRCode.toString(url, { type: "terminal", small: true }));
console.log("  Phones must be on the same Wi-Fi. On Windows, allow Node.js on private networks when the firewall asks.\n");
