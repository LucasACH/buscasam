import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import BuscarPage from "./page";

const replace = vi.fn();
const searchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => searchParams,
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <BuscarPage />
    </QueryClientProvider>,
  );
}

describe("/buscar empty-q guard", () => {
  beforeEach(() => {
    replace.mockReset();
    Array.from(searchParams.keys()).forEach((k) => searchParams.delete(k));
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ results: [], total: 0, saturated: false }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("does not call /api/search when q is empty", async () => {
    renderPage();
    await new Promise((r) => setTimeout(r, 50));
    const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls;
    const searchCalls = calls.filter(([url]) =>
      String(url).includes("/api/search"),
    );
    expect(searchCalls).toHaveLength(0);
  });
});
