import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { toastMock } = vi.hoisted(() => ({ toastMock: vi.fn() }));
vi.mock("sonner", () => ({
  toast: Object.assign(toastMock, { info: toastMock, warning: toastMock }),
}));

import { withAuthToast } from "./client";

describe("withAuthToast fetch wrapper", () => {
  beforeEach(() => {
    toastMock.mockReset();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fires the soft toast on 401 for unsafe methods", async () => {
    const inner = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 401 }));
    const wrapped = withAuthToast(inner);

    await wrapped(
      new Request("http://test/api/auth/logout", { method: "POST" }),
    );

    expect(toastMock).toHaveBeenCalledTimes(1);
    expect(String(toastMock.mock.calls[0]![0])).toMatch(/Iniciá sesión/i);
  });

  it("does NOT fire on 401 for safe reads", async () => {
    const inner = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 401 }));
    const wrapped = withAuthToast(inner);

    await wrapped(new Request("http://test/api/me", { method: "GET" }));

    expect(toastMock).not.toHaveBeenCalled();
  });

  it("does NOT fire on a 200 response, even for unsafe methods", async () => {
    const inner = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 204 }));
    const wrapped = withAuthToast(inner);

    await wrapped(
      new Request("http://test/api/auth/logout", { method: "POST" }),
    );

    expect(toastMock).not.toHaveBeenCalled();
  });
});
