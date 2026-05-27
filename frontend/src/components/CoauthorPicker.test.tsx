import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { CoauthorPicker } from "./CoauthorPicker";

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const HITS = [
  { user_id: 11, name: "Ada Lovelace", email_local: "ada", picture_url: null },
  { user_id: 12, name: "Adam Smith", email_local: "asmith", picture_url: null },
];

function mockSearch() {
  return vi.spyOn(global, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : (input as Request).url;
    if (url.includes("/api/users/search")) {
      return new Response(JSON.stringify(HITS), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response("", { status: 404 });
  });
}

describe("CoauthorPicker", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.spyOn(global, "fetch").mockReset();
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("debounces /api/users/search while the user types", async () => {
    const fetchSpy = mockSearch();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    wrap(<CoauthorPicker value={[]} onChange={() => {}} />);

    const input = screen.getByRole("textbox", { name: /coautor/i });
    await user.type(input, "Ada");

    // Within the debounce window, no fetch yet.
    expect(
      fetchSpy.mock.calls.filter(([u]) =>
        typeof u === "string" ? u.includes("/api/users/search") : false,
      ),
    ).toHaveLength(0);

    await act(async () => {
      vi.advanceTimersByTime(250);
    });

    await waitFor(() => {
      const searchCalls = fetchSpy.mock.calls.filter(([u]) =>
        typeof u === "string" ? u.includes("/api/users/search") : false,
      );
      expect(searchCalls.length).toBeGreaterThan(0);
      const url = searchCalls[searchCalls.length - 1][0] as string;
      expect(url).toMatch(/q=Ada/);
    });
  });

  it("renders hits and selecting one emits the user_id + renders a chip", async () => {
    mockSearch();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onChange = vi.fn();

    wrap(<CoauthorPicker value={[]} onChange={onChange} />);

    await user.type(screen.getByRole("textbox", { name: /coautor/i }), "Ada");
    await act(async () => {
      vi.advanceTimersByTime(250);
    });

    const hit = await screen.findByRole("option", { name: /Ada Lovelace/ });
    await user.click(hit);

    expect(onChange).toHaveBeenLastCalledWith([11]);
    expect(screen.getByText(/Ada Lovelace/)).toBeInTheDocument();
  });

  it("removes a chip when its Quitar button is clicked", async () => {
    mockSearch();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onChange = vi.fn();

    wrap(<CoauthorPicker value={[]} onChange={onChange} />);

    await user.type(screen.getByRole("textbox", { name: /coautor/i }), "Ada");
    await act(async () => {
      vi.advanceTimersByTime(250);
    });
    await user.click(await screen.findByRole("option", { name: /Ada Lovelace/ }));

    const remove = await screen.findByRole("button", {
      name: /Quitar Ada Lovelace/i,
    });
    await user.click(remove);

    expect(onChange).toHaveBeenLastCalledWith([]);
    expect(screen.queryByText("Ada Lovelace")).toBeNull();
  });
});
