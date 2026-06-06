"use client";

import { useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { RetryMutationError } from "@/app/mis-trabajos/useDraftState";

function secondsUntil(iso: string | null): number {
  if (!iso) return 0;
  return Math.max(0, Math.ceil((Date.parse(iso) - Date.now()) / 1000));
}

// Reintentar for 'system' indexing failures: disabled with a mm:ss countdown
// until retry_available_at (the server-enforced cooldown), then enabled. The
// server stays the authority — a clock-skewed early click just 409s and the
// action re-syncs the draft state.
export function RetryIndexingButton({
  retryAvailableAt,
  retry,
  size,
}: {
  retryAvailableAt: string | null;
  retry: () => Promise<RetryMutationError | undefined>;
  size?: "sm" | "default";
}) {
  // secondsLeft derives from `now` at render; the interval only advances the
  // clock, so a retryAvailableAt change reflects immediately on re-render.
  const [now, setNow] = useState(() => Date.now());
  const [retrying, setRetrying] = useState(false);
  const secondsLeft = retryAvailableAt
    ? Math.max(0, Math.ceil((Date.parse(retryAvailableAt) - now) / 1000))
    : 0;

  useEffect(() => {
    if (secondsUntil(retryAvailableAt) === 0) return;
    const timer = setInterval(() => {
      setNow(Date.now());
      if (secondsUntil(retryAvailableAt) === 0) clearInterval(timer);
    }, 1000);
    return () => clearInterval(timer);
  }, [retryAvailableAt]);

  async function onRetry() {
    setRetrying(true);
    try {
      const err = await retry();
      if (err) toast.error("No se pudo reintentar");
    } finally {
      setRetrying(false);
    }
  }

  const mm = Math.floor(secondsLeft / 60);
  const ss = String(secondsLeft % 60).padStart(2, "0");
  return (
    <Button
      data-testid="retry-indexing"
      size={size}
      disabled={secondsLeft > 0 || retrying}
      onClick={onRetry}
    >
      <RotateCcw className="size-3.5" strokeWidth={1.9} />
      {secondsLeft > 0 ? `Reintentar en ${mm}:${ss}` : "Reintentar"}
    </Button>
  );
}
