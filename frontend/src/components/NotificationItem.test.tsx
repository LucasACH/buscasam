import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { NotificationDTO } from "@/lib/useNotifications";
import { NotificationItem } from "./NotificationItem";

const { markRead } = vi.hoisted(() => ({ markRead: vi.fn() }));
vi.mock("@/lib/useNotifications", () => ({
  useNotifications: () => ({ markRead }),
}));

function item(over: Partial<NotificationDTO>): NotificationDTO {
  return {
    id: 1,
    kind: "coauthor_invite",
    payload: {},
    read_at: null,
    created_at: "2026-01-01T00:00:00Z",
    ...over,
  } as NotificationDTO;
}

describe("NotificationItem per-kind renderers", () => {
  beforeEach(() => markRead.mockReset());
  afterEach(() => cleanup());

  it("coauthor_invite: shows title + inviter", () => {
    render(
      <NotificationItem
        item={item({
          kind: "coauthor_invite",
          payload: { doc_title: "Redes neuronales", inviter: "Ada Lovelace" },
        })}
      />,
    );
    expect(screen.getByText(/Redes neuronales/)).toBeInTheDocument();
    expect(screen.getByText(/Ada Lovelace/)).toBeInTheDocument();
  });

  it("document_hidden: shows title + reason", () => {
    render(
      <NotificationItem
        item={item({
          kind: "document_hidden",
          payload: { doc_title: "Grafos", reason: "contenido duplicado" },
        })}
      />,
    );
    expect(screen.getByText(/Grafos/)).toBeInTheDocument();
    expect(screen.getByText(/contenido duplicado/)).toBeInTheDocument();
  });

  it("document_unhidden: shows title + note", () => {
    render(
      <NotificationItem
        item={item({
          kind: "document_unhidden",
          payload: { doc_title: "Compiladores", note: "revisado y restaurado" },
        })}
      />,
    );
    expect(screen.getByText(/Compiladores/)).toBeInTheDocument();
    expect(screen.getByText(/revisado y restaurado/)).toBeInTheDocument();
  });

  it("processing_failed: shows title", () => {
    render(
      <NotificationItem
        item={item({
          kind: "processing_failed",
          payload: { doc_title: "Álgebra lineal" },
        })}
      />,
    );
    expect(screen.getByText(/Álgebra lineal/)).toBeInTheDocument();
  });

  it("degrades gracefully when payload fields are missing", () => {
    render(
      <NotificationItem item={item({ kind: "coauthor_invite", payload: {} })} />,
    );
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument();
    expect(screen.getByText(/Alguien/)).toBeInTheDocument();
    expect(screen.getByText(/sin título/)).toBeInTheDocument();
  });

  it("per-row 'Marcar como leída' calls markRead(id) when unread", async () => {
    render(
      <NotificationItem
        item={item({
          id: 42,
          read_at: null,
          payload: { doc_title: "Redes", inviter: "Ada" },
        })}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Marcar como leída/i }),
    );
    expect(markRead).toHaveBeenCalledWith(42);
  });

  it("read rows do not show the per-row mark affordance", () => {
    render(
      <NotificationItem
        item={item({
          read_at: "2026-01-01T00:00:00Z",
          payload: { doc_title: "Redes", inviter: "Ada" },
        })}
      />,
    );
    expect(
      screen.queryByRole("button", { name: /Marcar como leída/i }),
    ).not.toBeInTheDocument();
  });
});
