import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/api/client", () => ({ api: { GET: apiGet } }));

import { CoauthorPicker } from "./CoauthorPicker";

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function StatefulPicker({
  initial = [],
  onChangeSpy,
}: {
  initial?: number[];
  onChangeSpy?: (ids: number[]) => void;
}) {
  const [value, setValue] = useState<number[]>(initial);
  return (
    <CoauthorPicker
      value={value}
      onChange={(ids) => {
        setValue(ids);
        onChangeSpy?.(ids);
      }}
    />
  );
}

const HITS = [
  { user_id: 11, name: "Ada Lovelace", email_local: "ada", picture_url: null },
  { user_id: 12, name: "Adam Smith", email_local: "asmith", picture_url: null },
];

describe("CoauthorPicker", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    apiGet.mockReset();
    apiGet.mockResolvedValue({ data: HITS });
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("debounces /api/users/search while the user types", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    wrap(<CoauthorPicker value={[]} onChange={() => {}} />);

    const input = screen.getByRole("textbox", { name: /coautor/i });
    await user.type(input, "Ada");

    // Within the debounce window, no fetch yet.
    expect(apiGet).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(250);
    });

    await waitFor(() => {
      expect(apiGet).toHaveBeenCalled();
      const lastCall = apiGet.mock.calls[apiGet.mock.calls.length - 1]!;
      expect(lastCall[0]).toBe("/api/users/search");
      expect(lastCall[1]).toMatchObject({ params: { query: { q: "Ada" } } });
    });
  });

  it("renders hits and selecting one emits the user_id + renders a chip", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onChange = vi.fn();

    wrap(<StatefulPicker onChangeSpy={onChange} />);

    await user.type(screen.getByRole("textbox", { name: /coautor/i }), "Ada");
    await act(async () => {
      vi.advanceTimersByTime(250);
    });

    const hit = await screen.findByRole("option", { name: /Ada Lovelace/ });
    await user.click(hit);

    expect(onChange).toHaveBeenLastCalledWith([11]);
    expect(
      await screen.findByRole("button", { name: /Quitar Ada Lovelace/i }),
    ).toBeInTheDocument();
  });

  it("removes a chip when its Quitar button is clicked", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onChange = vi.fn();

    wrap(<StatefulPicker onChangeSpy={onChange} />);

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
    expect(screen.queryByRole("button", { name: /Quitar Ada Lovelace/i })).toBeNull();
  });

  it("renders a chip for an initial value before any search", async () => {
    wrap(<StatefulPicker initial={[99]} />);

    // No name known yet → placeholder text + a working Quitar button.
    expect(
      await screen.findByRole("button", { name: /Quitar Usuario #99/i }),
    ).toBeInTheDocument();
  });

  it("drops chips when the parent resets value to []", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    function Harness() {
      const [value, setValue] = useState<number[]>([11]);
      return (
        <>
          <button type="button" onClick={() => setValue([])}>
            reset
          </button>
          <CoauthorPicker value={value} onChange={setValue} />
        </>
      );
    }
    wrap(<Harness />);

    expect(
      await screen.findByRole("button", { name: /Quitar Usuario #11/i }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "reset" }));

    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: /Quitar Usuario #11/i }),
      ).toBeNull(),
    );
  });
});
