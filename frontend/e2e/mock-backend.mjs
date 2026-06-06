// Mock backend for Playwright E2E. Holds an in-memory route registry that
// tests populate over a control plane:
//   PUT    /__mock/route      { path, status, body, contentType, headers }
//   GET    /__mock/recorded   → [{ method, path, headers, body }] received reqs
//   DELETE /__mock/reset
// Any other GET/HEAD path returns the registered response or 404; mutating
// methods (e.g. the SSR search/click POST) are recorded and answered 204. Used
// by SSR-driven specs that need fetchDetail to resolve to a known body and that
// assert server-side calls the browser can't intercept.
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_PORT ?? "8000");
const registry = new Map();
const recorded = [];

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
    const {
      path: routePath,
      status,
      body,
      contentType,
      headers,
    } = JSON.parse(raw);
    registry.set(routePath, {
      status: status ?? 200,
      body: typeof body === "string" ? body : JSON.stringify(body ?? null),
      contentType: contentType ?? "application/json",
      headers: headers ?? {},
    });
    return send(res, 204, "");
  }

  if (req.method === "GET" && path === "/__mock/recorded") {
    return send(res, 200, JSON.stringify(recorded), {
      "Content-Type": "application/json",
    });
  }

  if (req.method === "DELETE" && path === "/__mock/reset") {
    registry.clear();
    recorded.length = 0;
    return send(res, 204, "");
  }

  // Record every non-control-plane request so specs can assert SSR-side calls
  // (e.g. the relevance search/click POST) and the headers they carry.
  const reqBody =
    req.method === "GET" || req.method === "HEAD" ? "" : await readBody(req);
  recorded.push({ method: req.method, path, headers: req.headers, body: reqBody });

  const entry = registry.get(path);
  if (entry) {
    return send(res, entry.status, entry.body, {
      "Content-Type": entry.contentType,
      ...entry.headers,
    });
  }
  // Unregistered: instrumentation POSTs succeed as 204 (mirrors the real
  // fire-and-forget endpoint); GET/HEAD stay 404 as before.
  if (req.method === "GET" || req.method === "HEAD") return send(res, 404, "");
  return send(res, 204, "");
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`[mock-backend] listening on http://127.0.0.1:${PORT}`);
});
