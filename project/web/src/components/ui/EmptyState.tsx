import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: ReactNode;
  action?: ReactNode;
  tone?: "neutral" | "critical";
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
          "mb-4 flex size-11 items-center justify-center rounded-card border",
          tone === "critical"
            ? "border-critical/30 bg-critical-soft text-critical"
            : "border-line bg-surface-raised text-fg-subtle",
        )}
      >
        <Icon aria-hidden className="size-5" />
      </div>
      <h3 className="text-sm font-semibold text-fg">{title}</h3>
      <p className="mt-1.5 max-w-sm text-[0.8125rem] leading-relaxed text-fg-muted">
        {description}
      </p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
