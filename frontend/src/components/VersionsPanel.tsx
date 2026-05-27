"use client";

import { useState } from "react";

import { useVersionDownload } from "@/app/docs/[id]/useVersionDownload";
import type { DetailVersion } from "@/app/docs/[id]/types";
import { formatBytes } from "@/lib/utils";

type Props = {
  docId: number;
  versions: DetailVersion[] | undefined;
  canManage: boolean;
};

export function VersionsPanel({ docId, versions, canManage }: Props) {
  const download = useVersionDownload(docId);
  const [error, setError] = useState(false);

  if (!canManage || versions == null) return null;

  const ordered = [...versions].sort((a, b) => b.n - a.n);

  async function onDownload(n: number) {
    setError(false);
    try {
      await download(n);
    } catch {
      // The rare revoke-mid-session race: the version was readable at detail
      // load but the preflight 404'd. Surface inline, no toast (module map).
      setError(true);
    }
  }

  return (
    <section className="mt-6">
      <h2 className="text-sm font-medium">Versiones anteriores</h2>
      {error && (
        <p className="text-destructive mt-2 text-sm">
          No se pudo descargar esta versión
        </p>
      )}
      <ul className="mt-2 space-y-2 text-sm">
        {ordered.map((v) => (
          <li
            key={v.n}
            className="border-border flex items-center justify-between gap-3 rounded-lg border p-3"
          >
            <span className="truncate">
              v{v.n} · {v.original_filename} · {formatBytes(v.size_bytes)}
              {v.indexed_at && ` · ${v.indexed_at.slice(0, 10)}`}
              {v.is_current && " (actual)"}
            </span>
            <button
              type="button"
              aria-label={`Descargar versión ${v.n}`}
              className="text-primary text-sm underline-offset-2 hover:underline"
              onClick={() => onDownload(v.n)}
            >
              Descargar
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
