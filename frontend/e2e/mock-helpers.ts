const MOCK_PORT = process.env.MOCK_PORT ?? "8000";
const BASE = `http://127.0.0.1:${MOCK_PORT}`;

type Route = {
  path: string;
  status?: number;
  body?: unknown;
  contentType?: string;
  headers?: Record<string, string>;
};

export async function setMockRoute(route: Route): Promise<void> {
  const r = await fetch(`${BASE}/__mock/route`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(route),
  });
  if (!r.ok) throw new Error(`setMockRoute failed: ${r.status}`);
}

export async function resetMocks(): Promise<void> {
  const r = await fetch(`${BASE}/__mock/reset`, { method: "DELETE" });
  if (!r.ok) throw new Error(`resetMocks failed: ${r.status}`);
}
