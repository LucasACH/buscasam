import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { accept, decline, refresh } = vi.hoisted(() => ({
  accept: vi.fn(),
  decline: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("@/lib/useCoauthorInvitation", () => ({
  useCoauthorInvitation: () => ({ accept, decline }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

import { CoauthorInvitationBanner } from "./CoauthorInvitationBanner";

function renderBanner(variant: "minimal" | "banner" = "minimal") {
  render(
    <CoauthorInvitationBanner
      docId={7}
      titulo="Redes neuronales"
      inviter="Ada Lovelace"
      variant={variant}
    />,
  );
}

describe("CoauthorInvitationBanner", () => {
  beforeEach(() => {
    accept.mockReset().mockResolvedValue(undefined);
    decline.mockReset().mockResolvedValue(undefined);
    refresh.mockReset();
  });
  afterEach(() => cleanup());

  it("shows título, inviter, and both buttons in either variant", () => {
    renderBanner("banner");
    expect(screen.getByText(/Ada Lovelace/)).toBeInTheDocument();
    expect(screen.getByText(/Redes neuronales/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Aceptar/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Rechazar/i }),
    ).toBeInTheDocument();
  });

  it("Aceptar accepts the invitation then refreshes the SSR page", async () => {
    renderBanner();
    await userEvent.click(screen.getByRole("button", { name: /Aceptar/i }));
    expect(accept).toHaveBeenCalledWith(7);
    expect(refresh).toHaveBeenCalled();
  });

  it("Rechazar declines the invitation then refreshes the SSR page", async () => {
    renderBanner();
    await userEvent.click(screen.getByRole("button", { name: /Rechazar/i }));
    expect(decline).toHaveBeenCalledWith(7);
    expect(refresh).toHaveBeenCalled();
  });

  it("a 404 (gone) still refreshes so the stale invite resolves", async () => {
    accept.mockResolvedValue({ kind: "gone" });
    renderBanner();
    await userEvent.click(screen.getByRole("button", { name: /Aceptar/i }));
    expect(refresh).toHaveBeenCalled();
  });

  it("a network error surfaces inline and does not refresh", async () => {
    accept.mockResolvedValue({ kind: "network" });
    renderBanner();
    await userEvent.click(screen.getByRole("button", { name: /Aceptar/i }));
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
