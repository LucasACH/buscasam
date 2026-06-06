import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock("sonner", () => ({ toast: { error: toastError } }));

import { RetryIndexingButton } from "./RetryIndexingButton";

const retry = vi.fn();

describe("RetryIndexingButton", () => {
  beforeEach(() => {
    retry.mockReset();
    retry.mockResolvedValue(undefined);
    toastError.mockReset();
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("is enabled immediately when the cooldown already elapsed", () => {
    render(
      <RetryIndexingButton
        retryAvailableAt="2020-01-01T00:00:00+00:00"
        retry={retry}
      />,
    );

    const button = screen.getByTestId("retry-indexing");
    expect(button).toBeEnabled();
    expect(button).toHaveTextContent("Reintentar");
  });

  it("counts down while inside the cooldown, then enables", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-06T12:00:00+00:00"));
    render(
      <RetryIndexingButton
        retryAvailableAt="2026-06-06T12:01:30+00:00"
        retry={retry}
      />,
    );

    const button = screen.getByTestId("retry-indexing");
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent("Reintentar en 1:30");

    await act(() => vi.advanceTimersByTimeAsync(60_000));
    expect(button).toHaveTextContent("Reintentar en 0:30");

    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(button).toBeEnabled();
    expect(button).toHaveTextContent("Reintentar");
  });

  it("delegates the click to retry()", async () => {
    const user = userEvent.setup();
    render(<RetryIndexingButton retryAvailableAt={null} retry={retry} />);

    await user.click(screen.getByTestId("retry-indexing"));

    expect(retry).toHaveBeenCalledTimes(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it("toasts when the retry fails", async () => {
    retry.mockResolvedValue("retry_failed");
    const user = userEvent.setup();
    render(<RetryIndexingButton retryAvailableAt={null} retry={retry} />);

    await user.click(screen.getByTestId("retry-indexing"));

    expect(toastError).toHaveBeenCalledWith("No se pudo reintentar");
  });
});
