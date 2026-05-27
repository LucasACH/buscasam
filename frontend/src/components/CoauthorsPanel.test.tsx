import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { useCoauthorsMock, invite, revoke } = vi.hoisted(() => ({
  useCoauthorsMock: vi.fn(),
  invite: vi.fn(),
  revoke: vi.fn(),
}));
vi.mock("@/app/mis-trabajos/[id]/editar/useCoauthors", () => ({
  useCoauthors: useCoauthorsMock,
}));

const { CoauthorPickerMock } = vi.hoisted(() => ({
  CoauthorPickerMock: vi.fn(),
}));
vi.mock("./CoauthorPicker", () => ({ CoauthorPicker: CoauthorPickerMock }));

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock("sonner", () => ({ toast: { error: toastError } }));

import { CoauthorsPanel } from "./CoauthorsPanel";

type CoauthorRow = {
  user_id: number | null;
  display_name: string;
  email_local: string | null;
  status: string;
};

function setup({
  isOwner,
  coauthors,
}: {
  isOwner: boolean;
  coauthors: CoauthorRow[];
}) {
  useCoauthorsMock.mockReturnValue({
    isOwner,
    coauthors,
    isLoading: false,
    isError: false,
    invite,
    revoke,
  });
  CoauthorPickerMock.mockImplementation(
    ({ onChange }: { value: number[]; onChange: (ids: number[]) => void }) => (
      <button
        type="button"
        data-testid="pick"
        onClick={() => onChange([42, 7])}
      >
        pick
      </button>
    ),
  );
}

describe("CoauthorsPanel", () => {
  beforeEach(() => {
    useCoauthorsMock.mockReset();
    invite.mockReset();
    invite.mockResolvedValue(undefined);
    revoke.mockReset();
    revoke.mockResolvedValue(undefined);
    CoauthorPickerMock.mockReset();
    toastError.mockReset();
  });
  afterEach(() => cleanup());

  it("renders nothing for non-owners", () => {
    setup({ isOwner: false, coauthors: [] });
    const { container } = render(<CoauthorsPanel docId={1} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("lists rows with status pills, Vos label on the owner row", () => {
    setup({
      isOwner: true,
      coauthors: [
        { user_id: 1, display_name: "Ada", email_local: "ada", status: "owner" },
        { user_id: 2, display_name: "Bob", email_local: "bob", status: "pending" },
        { user_id: 3, display_name: "Carla", email_local: "carla", status: "accepted" },
        { user_id: 4, display_name: "Dora", email_local: "dora", status: "declined" },
        { user_id: null, display_name: "Ed", email_local: null, status: "external" },
      ],
    });
    render(<CoauthorsPanel docId={1} />);

    expect(screen.getByText(/Ada/)).toBeInTheDocument();
    expect(screen.getByText(/Vos/)).toBeInTheDocument();
    expect(screen.getByText("Pendiente")).toBeInTheDocument();
    expect(screen.getByText("Aceptado")).toBeInTheDocument();
    expect(screen.getByText("Rechazado")).toBeInTheDocument();
  });

  it("shows Quitar only on Pendiente rows (not accepted, declined, or external)", () => {
    setup({
      isOwner: true,
      coauthors: [
        { user_id: 1, display_name: "Ada", email_local: "ada", status: "owner" },
        { user_id: 2, display_name: "Bob", email_local: "bob", status: "pending" },
        { user_id: 3, display_name: "Carla", email_local: "carla", status: "accepted" },
        { user_id: 4, display_name: "Dora", email_local: "dora", status: "declined" },
        { user_id: null, display_name: "Ed", email_local: null, status: "external" },
      ],
    });
    render(<CoauthorsPanel docId={1} />);

    const quitarButtons = screen.getAllByRole("button", { name: /Quitar/i });
    expect(quitarButtons).toHaveLength(1);
    expect(quitarButtons[0]).toHaveAccessibleName(/Bob/);
  });

  it("calls revoke with the user_id when Quitar is clicked", async () => {
    const user = userEvent.setup();
    setup({
      isOwner: true,
      coauthors: [
        { user_id: 1, display_name: "Ada", email_local: "ada", status: "owner" },
        { user_id: 2, display_name: "Bob", email_local: "bob", status: "pending" },
      ],
    });
    render(<CoauthorsPanel docId={1} />);

    await user.click(screen.getByRole("button", { name: /Quitar/i }));

    expect(revoke).toHaveBeenCalledWith(2);
  });

  it("filters already-listed users from picker selections before inviting", async () => {
    const user = userEvent.setup();
    setup({
      isOwner: true,
      coauthors: [
        { user_id: 1, display_name: "Ada", email_local: "ada", status: "owner" },
        { user_id: 42, display_name: "Already", email_local: "al", status: "pending" },
      ],
    });
    render(<CoauthorsPanel docId={1} />);

    // Picker reports two selections: 42 (already listed) and 7 (new).
    await user.click(screen.getByTestId("pick"));

    expect(invite).toHaveBeenCalledTimes(1);
    expect(invite).toHaveBeenCalledWith(7);
  });

  it("surfaces a 409 race from invite as an inline error", async () => {
    const user = userEvent.setup();
    invite.mockResolvedValue({ kind: "already_listed" });
    setup({
      isOwner: true,
      coauthors: [
        { user_id: 1, display_name: "Ada", email_local: "ada", status: "owner" },
      ],
    });
    render(<CoauthorsPanel docId={1} />);

    await user.click(screen.getByTestId("pick"));

    expect(toastError).toHaveBeenCalled();
  });
});
