"use client";

import { useState } from "react";
import { MoreHorizontal } from "lucide-react";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

function Sep() {
  return <span className="text-muted-foreground/60">›</span>;
}

// Collapse a long área path to `first › … › last`. The elided middle segments
// reveal on hover (desktop) or tap (mobile, via controlled open state).
export function AreaBreadcrumb({ areaName }: { areaName: string }) {
  const [open, setOpen] = useState(false);
  const crumbs = areaName.split(" › ");

  if (crumbs.length <= 3) {
    return (
      <>
        {crumbs.map((crumb, i) => (
          <span key={i} className="flex items-center gap-x-1.5">
            {i > 0 && <Sep />}
            <span className="break-words">{crumb}</span>
          </span>
        ))}
      </>
    );
  }

  const middle = crumbs.slice(1, -1);
  return (
    <>
      <span className="break-words">{crumbs[0]}</span>
      <Sep />
      <Tooltip open={open} onOpenChange={setOpen} delayDuration={0}>
        <TooltipTrigger
          onClick={() => setOpen((o) => !o)}
          className="text-muted-foreground inline-flex cursor-pointer items-end self-end"
          aria-label="Ver niveles intermedios"
        >
          <MoreHorizontal className="size-4" />
        </TooltipTrigger>
        <TooltipContent>{middle.join(" › ")}</TooltipContent>
      </Tooltip>
      <Sep />
      <span className="break-words">{crumbs[crumbs.length - 1]}</span>
    </>
  );
}
