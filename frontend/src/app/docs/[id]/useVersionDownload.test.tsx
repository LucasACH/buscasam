import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";

import { useVersionDownload } from "./useVersionDownload";

const URL_N2 = "/api/docs/42/versions/2/download";

// jsdom's window.location.assign is non-configurable; replace the whole
// location object (the property itself is configurable) with a spyable stub.
const assign = vi.fn();
let originalLocation: Location;

describe("useVersionDownload", () => {
  beforeEach(() => {
    assign.mockReset();
    originalLocation = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { assign },
    });
  });
  afterEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
    vi.restoreAllMocks();
  });

  it("HEAD-preflights then navigates to the download URL on 200", async () => {
    const fetchSpy = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(new Response("", { status: 200 }));

    const { result } = renderHook(() => useVersionDownload(42));
    await result.current(2);

    expect(fetchSpy).toHaveBeenCalledWith(
      URL_N2,
      expect.objectContaining({ method: "HEAD" }),
    );
    expect(assign).toHaveBeenCalledWith(URL_N2);
  });

  it("rejects and does not navigate when the preflight 404s", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response("", { status: 404 }),
    );

    const { result } = renderHook(() => useVersionDownload(42));

    await expect(result.current(99)).rejects.toThrow();
    expect(assign).not.toHaveBeenCalled();
  });
});
