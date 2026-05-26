import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { NotificationDTO } from "@/lib/useNotifications";
import { BandejaPanel } from "./BandejaPanel";

const { useNotificationsMock, markAllRead, markRead } = vi.hoisted(() => ({
  useNotificationsMock: vi.fn(),
  markAllRead: vi.fn(),
  markRead: vi.fn(),
}));
vi.mock("@/lib/useNotifications", () => ({
  useNotifications: () => useNotificationsMock(),
}));

function notif(id: number, read: boolean): NotificationDTO {
  return {
    id,
    kind: "coauthor_invite",
    payload: { doc_title: `Doc ${id}`, inviter: "Ada" },
    read_at: read ? "2026-01-01T00:00:00Z" : null,
    created_at: "2026-01-01T00:00:00Z",
  } as NotificationDTO;
}

function mockHook(items: NotificationDTO[]) {
  useNotificationsMock.mockReturnValue({
    items,
    isLoading: false,
    markRead,
    markAllRead,
  });
}

describe("BandejaPanel", () => {
  beforeEach(() => {
    useNotificationsMock.mockReset();
    markAllRead.mockReset();
    markRead.mockReset();
  });
  afterEach(() => cleanup());

  it("renders an item per notification", () => {
    mockHook([notif(1, false), notif(2, true)]);
    render(<BandejaPanel />);
    expect(screen.getByText(/Doc 1/)).toBeInTheDocument();
    expect(screen.getByText(/Doc 2/)).toBeInTheDocument();
  });

  it("shows the empty state when there are no notifications", () => {
    mockHook([]);
    render(<BandejaPanel />);
    expect(screen.getByText(/No tenés notificaciones/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Marcar todas como leídas/i }),
    ).not.toBeInTheDocument();
  });

  it("shows the bulk footer and calls markAllRead when unread remain", async () => {
    mockHook([notif(1, false), notif(2, true)]);
    render(<BandejaPanel />);
    await userEvent.click(
      screen.getByRole("button", { name: /Marcar todas como leídas/i }),
    );
    expect(markAllRead).toHaveBeenCalledTimes(1);
  });

  it("hides the bulk footer when every notification is read", () => {
    mockHook([notif(1, true), notif(2, true)]);
    render(<BandejaPanel />);
    expect(
      screen.queryByRole("button", { name: /Marcar todas como leídas/i }),
    ).not.toBeInTheDocument();
  });
});
