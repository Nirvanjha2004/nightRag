import { useId } from "react";
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const CONTROL =
  "w-full rounded-control border border-line bg-surface-raised px-3 text-sm text-fg " +
  "placeholder:text-fg-subtle transition-colors " +
  "hover:border-line-strong focus:border-accent focus:outline-none " +
  "disabled:cursor-not-allowed disabled:bg-surface disabled:text-fg-subtle";

interface FieldProps {
  label: string;
  hint?: ReactNode;
  /** Rendered as an alert and wired to the control via aria-describedby. */
  error?: string;
  children: (props: { id: string; describedBy: string | undefined }) => ReactNode;
  className?: string;
}

/** Label + control + hint/error, wired together for screen readers. */
export function Field({ label, hint, error, children, className }: FieldProps) {
  const id = useId();
  const hintId = hint || error ? `${id}-hint` : undefined;

  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={id} className="block text-[0.8125rem] font-medium text-fg">
        {label}
      </label>
      {children({ id, describedBy: hintId })}
      {(hint || error) && (
        <p
          id={hintId}
          role={error ? "alert" : undefined}
          className={cn("text-xs leading-relaxed", error ? "text-critical" : "text-fg-muted")}
        >
          {error ?? hint}
        </p>
      )}
    </div>
  );
}

export function TextInput({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(CONTROL, "h-10", className)} {...props} />;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  children: ReactNode;
}

export function Select({ className, children, ...props }: SelectProps) {
  return (
    <div className="relative">
      <select className={cn(CONTROL, "h-10 appearance-none pr-9", className)} {...props}>
        {children}
      </select>
      <ChevronDown
        aria-hidden
        className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-fg-subtle"
      />
    </div>
  );
}

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}

/** A switch that also states its on/off value in words, not just position. */
export function Toggle({ checked, onChange, label, description, disabled }: ToggleProps) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <label htmlFor={id} className="block text-[0.8125rem] font-medium text-fg">
          {label}
        </label>
        {description && <p className="mt-1 text-xs leading-relaxed text-fg-muted">{description}</p>}
      </div>
      <button
        type="button"
        id={id}
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative mt-0.5 h-6 w-11 shrink-0 rounded-pill border transition-colors duration-200",
          "disabled:cursor-not-allowed disabled:opacity-50",
          checked ? "border-accent bg-accent" : "border-line-strong bg-surface-hover",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 flex size-4 items-center justify-center rounded-pill transition-all duration-200",
            checked ? "left-[1.5rem] bg-fg-inverse" : "left-0.5 bg-fg-subtle",
          )}
        >
          {checked && <Check aria-hidden className="size-3 text-accent" strokeWidth={3} />}
        </span>
        <span className="sr-only">{checked ? "On" : "Off"}</span>
      </button>
    </div>
  );
}

interface SliderProps {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
  label: string;
  hint?: string;
  /** Shown next to the label — the current value in the units the user thinks in. */
  display?: string;
}

export function Slider({
  value,
  min,
  max,
  step = 1,
  onChange,
  label,
  hint,
  display,
}: SliderProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const percent = ((value - min) / (max - min)) * 100;

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-[0.8125rem] font-medium text-fg">
          {label}
        </label>
        <span className="font-mono text-xs tabular-nums text-accent">{display ?? value}</span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-describedby={hintId}
        onChange={(event) => onChange(Number(event.target.value))}
        // The filled portion is painted with a gradient stop at the current
        // value, so the track needs no extra element to style.
        style={{
          background: `linear-gradient(to right, var(--color-accent) ${percent}%, var(--color-line-strong) ${percent}%)`,
        }}
        className={cn(
          "h-1.5 w-full cursor-pointer appearance-none rounded-pill",
          "[&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:size-4",
          "[&::-webkit-slider-thumb]:rounded-pill [&::-webkit-slider-thumb]:bg-accent",
          "[&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-surface",
          "[&::-webkit-slider-thumb]:transition-transform hover:[&::-webkit-slider-thumb]:scale-110",
          "[&::-moz-range-thumb]:size-4 [&::-moz-range-thumb]:rounded-pill",
          "[&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-surface",
          "[&::-moz-range-thumb]:bg-accent",
        )}
      />
      {hint && (
        <p id={hintId} className="text-xs leading-relaxed text-fg-muted">
          {hint}
        </p>
      )}
    </div>
  );
}
