import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import http from "node:http";
import { createRequire } from "node:module";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import test from "node:test";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

async function listen(server) {
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  return server.address().port;
}

async function close(server) {
  if (!server.listening) return;
  server.closeAllConnections();
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
}

test("built frontend uses the same bounded API proxy outside Vercel", { timeout: 30_000 }, async (t) => {
  const upstream = http.createServer(async (request, response) => {
    let bytes = 0;
    for await (const chunk of request) bytes += chunk.length;
    if (request.url === "/api/slow") await delay(2_000);
    if (response.destroyed) return;
    if (request.url === "/api/private" && request.headers["x-api-key"] !== "synthetic-owner-key") {
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ detail: "Missing operator key" }));
      return;
    }
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ path: request.url, key: request.headers["x-api-key"] ?? null, bytes }));
  });
  const upstreamPort = await listen(upstream);
  const portReservation = http.createServer();
  const frontendPort = await listen(portReservation);
  await close(portReservation);
  const env = {
    ...process.env,
    BACKEND_API_URL: `http://127.0.0.1:${upstreamPort}`,
    API_PROXY_TIMEOUT_SECONDS: "1",
    NEXT_TELEMETRY_DISABLED: "1",
    SIM_API_KEY: "synthetic-admin-key-must-never-be-injected",
  };
  delete env.VERCEL;
  delete env.MAX_REQUEST_BYTES;
  const child = spawn(process.execPath, [require.resolve("next/dist/bin/next"), "start", "--hostname", "127.0.0.1", "--port", String(frontendPort)], {
    cwd: root, env, windowsHide: true, stdio: ["ignore", "pipe", "pipe"],
  });
  let logs = "";
  child.stdout.on("data", (chunk) => { logs = (logs + chunk).slice(-6000); });
  child.stderr.on("data", (chunk) => { logs = (logs + chunk).slice(-6000); });
  t.after(async () => {
    child.kill();
    await close(upstream);
  });
  const base = `http://127.0.0.1:${frontendPort}`;
  let ready = false;
  for (let attempt = 0; attempt < 100 && child.exitCode === null; attempt += 1) {
    try {
      if ((await fetch(base)).ok) { ready = true; break; }
    } catch { /* Wait only until the local process is ready. */ }
    await delay(100);
  }
  assert.ok(ready, `Build first with npm run build. Next failed to start: ${logs}`);

  await t.test("uses configured nondefault upstream, query and caller key", async () => {
    const response = await fetch(`${base}/api/echo?check=proxy`, { headers: { "X-API-Key": "synthetic-owner-key" } });
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { path: "/api/echo?check=proxy", key: "synthetic-owner-key", bytes: 0 });
  });
  await t.test("never gives anonymous requests the configured administrator key", async () => {
    const response = await fetch(`${base}/api/private`);
    assert.equal(response.status, 401);
    assert.deepEqual(await response.json(), { detail: "Missing operator key" });
  });
  await t.test("forwards a bounded upload and rejects a request above 4 MB", async () => {
    const small = await fetch(`${base}/api/echo`, { method: "POST", body: "synthetic input" });
    assert.equal(small.status, 200);
    assert.equal((await small.json()).bytes, 15);
    const oversized = await fetch(`${base}/api/echo`, { method: "POST", body: new Uint8Array(4_000_001) });
    assert.equal(oversized.status, 413);
    assert.match((await oversized.json()).detail, /limit/i);
  });
  await t.test("returns a useful timeout instead of waiting indefinitely", async () => {
    const response = await fetch(`${base}/api/slow`);
    assert.equal(response.status, 504);
    assert.match((await response.json()).detail, /recent runs/i);
  });
  await t.test("returns a useful error when the backend is unavailable", async () => {
    await close(upstream);
    const response = await fetch(`${base}/api/echo`);
    assert.equal(response.status, 502);
    assert.deepEqual(await response.json(), { detail: "Simulation backend is unavailable" });
  });
});
