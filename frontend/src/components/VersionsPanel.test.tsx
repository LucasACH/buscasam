import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { downloadMock, useVersionDownloadMock } = vi.hoisted(() => ({
  downloadMock: vi.fn(),
  useVersionDownloadMock: vi.fn(),
}));
vi.mock("@/app/docs/[id]/useVersionDownload", () => ({
  useVersionDownload: useVersionDownloadMock,
}));

import { VersionsPanel } from "./VersionsPanel";
import type { DetailVersion } from "@/app/docs/[id]/types";

const VERSIONS: DetailVersion[] = [
  {
    n: 1,
    original_filename: "tesis_v1.pdf",
    mime: "application/pdf",
    size_bytes: 1000,
    indexed_at: "2024-01-01T10:00:00+00:00",
    is_current: false,
  },
  {
    n: 2,
    original_filename: "tesis_v2.pdf",
    mime: "application/pdf",
    size_bytes: 2048,
    indexed_at: "2024-02-01T10:00:00+00:00",
    is_current: true,
  },
];

describe("VersionsPanel", () => {
  beforeEach(() => {
    downloadMock.mockReset();
    downloadMock.mockResolvedValue(undefined);
    useVersionDownloadMock.mockReset();
    useVersionDownloadMock.mockReturnValue(downloadMock);
  });
  afterEach(() => cleanup());

  it("returns null when the viewer cannot manage", () => {
    const { container } = render(
      <VersionsPanel docId={42} versions={VERSIONS} canManage={false} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("returns null when versions is absent (reader payload)", () => {
    const { container } = render(
      <VersionsPanel docId={42} versions={undefined} canManage={true} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders one row per version, descending by n, current annotated (actual)", () => {
    render(<VersionsPanel docId={42} versions={VERSIONS} canManage={true} />);

    expect(screen.getByText("Versiones anteriores")).toBeInTheDocument();
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    // Descending: current (v2) first.
    expect(rows[0]).toHaveTextContent("v2");
    expect(rows[0]).toHaveTextContent("tesis_v2.pdf");
    expect(rows[0]).toHaveTextContent("2.0 KB");
    expect(rows[0]).toHaveTextContent("2024-02-01");
    expect(rows[0]).toHaveTextContent("(actual)");
    expect(rows[1]).toHaveTextContent("v1");
    expect(rows[1]).toHaveTextContent("tesis_v1.pdf");
    expect(rows[1]).not.toHaveTextContent("(actual)");
  });

  it("triggers the per-version download on click", async () => {
    const user = userEvent.setup();
    render(<VersionsPanel docId={42} versions={VERSIONS} canManage={true} />);

    await user.click(
      screen.getByRole("button", { name: /descargar versión 1/i }),
    );

    expect(downloadMock).toHaveBeenCalledWith(1);
  });

  it("surfaces an inline error when the download is rejected mid-session", async () => {
    const user = userEvent.setup();
    downloadMock.mockRejectedValue(new Error("HTTP 404"));
    render(<VersionsPanel docId={42} versions={VERSIONS} canManage={true} />);

    await user.click(
      screen.getByRole("button", { name: /descargar versión 2/i }),
    );

    await waitFor(() =>
      expect(
        screen.getByText("No se pudo descargar esta versión"),
      ).toBeInTheDocument(),
    );
  });
});
