import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export function Card({ className, children, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-panel border border-rule bg-panel",
        // Depth comes from the surface ramp plus one shared shadow token, not
        // from a different shadow invented per element.
        "shadow-[var(--shadow-panel)]",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

interface CardHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function CardHeader({ title, description, action, className }: CardHeaderProps) {
  return (
    <div className={cn("flex items-start justify-between gap-4 px-5 pt-5 pb-4", className)}>
      <div className="min-w-0">
        {/* The display face, like every other heading in the product — a card
            title set in the body face is where an identity quietly leaks away. */}
        <h2 className="display text-[0.9375rem] font-semibold tracking-tight text-moon">{title}</h2>
        {description && (
          <p className="mt-1 text-[0.8125rem] leading-relaxed text-moon-2">{description}</p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function CardBody({ className, children, ...props }: CardProps) {
  return (
    <div className={cn("px-5 pb-5", className)} {...props}>
      {children}
    </div>
  );
}
