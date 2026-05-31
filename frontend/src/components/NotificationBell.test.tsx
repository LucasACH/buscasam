import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { NotificationDTO } from "@/lib/useNotifications";
import { NotificationBell } from "./NotificationBell";

const { unreadMock, notifMock, markAllRead, markRead } = vi.hoisted(() => ({
  unreadMock: vi.fn(),
  notifMock: vi.fn(),
  markAllRead: vi.fn(),
  markRead: vi.fn(),
}));
vi.mock("@/lib/useNotifications", () => ({
  useNotifications: () => notifMock(),
  useUnreadCount: () => unreadMock(),
}));
vi.mock("@/lib/useCoauthorInvitation", () => ({
  useCoauthorInvitation: () => ({ accept: vi.fn(), decline: vi.fn() }),
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

function setup({ count, items }: { count: number; items: NotificationDTO[] }) {
  unreadMock.mockReturnValue({ count, isLoading: false });
  notifMock.mockReturnValue({ items, isLoading: false, markRead, markAllRead });
}

describe("NotificationBell", () => {
  beforeEach(() => {
    unreadMock.mockReset();
    notifMock.mockReset();
    markAllRead.mockReset();
    markRead.mockReset();
  });
  afterEach(() => cleanup());

  it("shows a numeric badge when there are unread notifications", () => {
    setup({ count: 3, items: [] });
    render(<NotificationBell />);
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("shows no badge when the unread count is zero", () => {
    setup({ count: 0, items: [] });
    render(<NotificationBell />);
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("opening the popover renders the panel without marking everything read", async () => {
    setup({ count: 2, items: [notif(1, false), notif(2, false)] });
    render(<NotificationBell />);

    await userEvent.click(
      screen.getByRole("button", { name: /Notificaciones/i }),
    );

    // Auto-marking on open would hide the unread-gated invite actions before
    // the user can act on them; reads happen via explicit controls instead.
    expect(markAllRead).not.toHaveBeenCalled();
    expect(await screen.findByText(/Doc 1/)).toBeInTheDocument();
  });
});
