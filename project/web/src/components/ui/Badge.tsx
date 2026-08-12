import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Tones are named for what they mean in retrieval, not for their colour:
 * `keep` is what survived, `cut` is what did not, `lamp` is live or notable.
 */
type Tone = "neutral" | "lamp" | "keep" | "cut";

const TONES: Record<Tone, string> = {
  neutral: "bg-panel-2 text-moon-2 border-rule",
  lamp: "bg-lamp-soft text-lamp border-lamp-line",
  keep: "bg-keep-soft text-keep border-keep/30",
  cut: "bg-cut-soft text-cut border-cut/30",
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
        "inline-flex items-center gap-1.5 rounded-control border px-1.5 py-0.5",
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
