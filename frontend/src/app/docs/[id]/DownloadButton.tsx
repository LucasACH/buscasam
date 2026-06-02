"use client";

import posthog from "posthog-js";

import { Button } from "@/components/ui/button";

type Props = {
  docId: number;
  label: string;
  href: string;
  variant?: "default" | "outline";
  eventProperties?: Record<string, unknown>;
};

export function DownloadButton({
  docId,
  label,
  href,
  variant = "default",
  eventProperties,
}: Props) {
  return (
    <Button asChild size="sm" variant={variant}>
      <a
        href={href}
        download
        aria-label={label}
        onClick={() =>
          posthog.capture("document_downloaded", {
            doc_id: docId,
            ...eventProperties,
          })
        }
      >
        Descargar
      </a>
    </Button>
  );
}
