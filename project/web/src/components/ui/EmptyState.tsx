import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: ReactNode;
  action?: ReactNode;
  tone?: "neutral" | "cut";
  className?: string;
}

/** The screen shown when there is genuinely nothing — never a blank panel. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  tone = "neutral",
  className,
}: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center px-6 py-14 text-center", className)}>
      <div
        className={cn(
          "mb-4 flex size-11 items-center justify-center rounded-panel border",
          tone === "cut"
            ? "border-cut/30 bg-cut-soft text-cut"
            : "border-rule bg-panel text-moon-3",
        )}
      >
        <Icon aria-hidden className="size-5" />
      </div>
      <h3 className="text-sm font-semibold text-moon">{title}</h3>
      <p className="mt-1.5 max-w-sm text-[0.8125rem] leading-relaxed text-moon-2">
        {description}
      </p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
