import { cn } from "@/lib/utils";

export type BadgeTone = "neutral" | "amber" | "green" | "red" | "blue";

export const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: "bg-status-neutral-bg text-status-neutral-fg",
  amber: "bg-status-amber-bg text-status-amber-fg",
  green: "bg-status-green-bg text-status-green-fg",
  red: "bg-status-red-bg text-status-red-fg",
  blue: "bg-status-blue-bg text-status-blue-fg",
};

export function StatusBadge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: BadgeTone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-[22px] items-center gap-1 rounded-full px-[9px] text-xs font-medium whitespace-nowrap",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
