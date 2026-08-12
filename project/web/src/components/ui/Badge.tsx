import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

type Tone = "neutral" | "accent" | "positive" | "caution" | "critical";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-hover text-fg-muted border-line",
  accent: "bg-accent-soft text-accent border-accent-line",
  positive: "bg-positive-soft text-positive border-positive/30",
  caution: "bg-caution-soft text-caution border-caution/30",
  critical: "bg-critical-soft text-critical border-critical/30",
};

interface BadgeProps {
  tone?: Tone;
  /** Required whenever the tone carries meaning — colour alone never does. */
  icon?: LucideIcon;
  className?: string;
  children: ReactNode;
}

export function Badge({ tone = "neutral", icon: Icon, className, children }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill border px-2 py-0.5",
        "text-[0.6875rem] font-medium leading-5 whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {Icon && <Icon aria-hidden className="size-3 shrink-0" />}
      {children}
    </span>
  );
}
