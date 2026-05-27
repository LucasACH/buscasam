/* eslint-disable */
// Mock backend for Playwright E2E. Holds an in-memory route registry that
// tests populate over a control plane:
//   PUT    /__mock/route   { path, status, body, contentType, headers }
//   DELETE /__mock/reset
// Any other GET/HEAD path returns the registered response or 404. Used by
// SSR-driven specs that need fetchDetail to resolve to a known body.
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_PORT ?? "8000");
const registry = new Map();

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function send(res, status, body, headers = {}) {
  res.writeHead(status, headers);
  res.end(body);
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  const path = url.pathname;

  if (req.method === "GET" && path === "/__mock/health") {
    return send(res, 200, "ok", { "Content-Type": "text/plain" });
  }

  if (req.method === "PUT" && path === "/__mock/route") {
    const raw = await readBody(req);
    const { path: routePath, status, body, contentType, headers } = JSON.parse(
      raw,
    );
    registry.set(routePath, {
      status: status ?? 200,
      body: typeof body === "string" ? body : JSON.stringify(body ?? null),
      contentType: contentType ?? "application/json",
      headers: headers ?? {},
    });
    return send(res, 204, "");
  }

  if (req.method === "DELETE" && path === "/__mock/reset") {
    registry.clear();
    return send(res, 204, "");
  }

  const entry = registry.get(path);
  if (!entry) return send(res, 404, "");
  return send(res, entry.status, entry.body, {
    "Content-Type": entry.contentType,
    ...entry.headers,
  });
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`[mock-backend] listening on http://127.0.0.1:${PORT}`);
});
