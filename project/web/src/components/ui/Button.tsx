import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-lamp text-on-lamp hover:bg-lamp-2 active:brightness-95 " +
    "disabled:bg-rule-strong disabled:text-moon-3",
  secondary:
    "bg-panel text-moon border border-rule hover:bg-panel-2 " +
    "hover:border-rule-strong active:bg-panel disabled:text-moon-3",
  ghost:
    "text-moon-2 hover:text-moon hover:bg-panel-2 active:bg-panel " +
    "disabled:text-moon-3 disabled:hover:bg-transparent",
  danger:
    "bg-cut-soft text-cut border border-cut/30 hover:border-cut/60 " +
    "hover:bg-cut/15 disabled:text-moon-3",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-[0.8125rem] gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
};

/**
 * The button's visual recipe, without the element.
 *
 * Exported so a router `<Link>` can look identical to a button without being
 * wrapped in one — an `<a>` inside a `<button>` is invalid, and turning a
 * navigation into a click handler loses middle-click, Ctrl+click and the
 * status-bar URL preview.
 */
export function buttonClasses({
  variant = "secondary",
  size = "md",
  iconOnly = false,
  className,
}: {
  variant?: Variant;
  size?: Size;
  iconOnly?: boolean;
  className?: string;
} = {}): string {
  return cn(
    "inline-flex items-center justify-center rounded-control font-medium",
    "transition-colors duration-150 select-none",
    "disabled:cursor-not-allowed",
    VARIANTS[variant],
    SIZES[size],
    iconOnly && (size === "sm" ? "w-8 px-0" : "w-10 px-0"),
    className,
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  /** Icon-only buttons must still name themselves for screen readers. */
  iconOnly?: boolean;
  children?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "md",
    loading = false,
    iconOnly = false,
    className,
    disabled,
    children,
    ...props
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      // A loading button stays focusable but rejects clicks: removing it from
      // the tab order mid-interaction would drop the user's focus to <body>.
      aria-busy={loading || undefined}
      disabled={disabled || loading}
      className={buttonClasses({ variant, size, iconOnly, className })}
      {...props}
    >
      {loading && <Loader2 aria-hidden className="size-4 animate-spin" />}
      {children}
    </button>
  );
});
