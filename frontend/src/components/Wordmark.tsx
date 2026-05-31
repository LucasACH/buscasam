type WordmarkProps = {
  size?: "base" | "lg";
  className?: string;
};

const MARK_PX = { base: 26, lg: 38 } as const;

export function Wordmark({ size = "base", className }: WordmarkProps) {
  const px = MARK_PX[size];
  return (
    <span
      className={[
        "relative top-[2px] inline-flex select-none items-center font-semibold tracking-tight text-foreground",
        size === "lg" ? "gap-3 text-[34px]" : "gap-[9px] text-[21px]",
        "leading-none",
        className ?? "",
      ].join(" ")}
    >
      <svg
        width={px}
        height={px}
        viewBox="0 0 26 26"
        fill="none"
        aria-hidden
        className="shrink-0"
      >
        <rect width="26" height="26" rx="7.5" fill="var(--primary)" />
        <circle cx="11" cy="11" r="4.4" stroke="#fff" strokeWidth="2.1" />
        <path
          d="M14.4 14.4 18.5 18.5"
          stroke="#fff"
          strokeWidth="2.1"
          strokeLinecap="round"
        />
      </svg>
      <span>
        BUSCA<span className="text-primary">SAM</span>
      </span>
    </span>
  );
}
