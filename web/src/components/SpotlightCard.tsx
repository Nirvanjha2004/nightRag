import type { HTMLAttributes, MouseEvent as ReactMouseEvent, ReactNode } from "react";
import { motion, useMotionTemplate, useMotionValue } from "framer-motion";
import { cn } from "@/lib/utils";

/**
 * Aceternity's CardSpotlight, lightened for NightRag.
 *
 * The original paints a full motion-graphics canvas inside the glow; that is
 * more spectacle than this work surface wants, so the glow is kept and the
 * canvas is dropped. What remains is the part that reads as craftsmanship: a
 * copper wash that follows the cursor across the card's edge, masked so it
 * stays a halo rather than a stain.
 *
 * The wash is the theme's lamp at low alpha, so it stays warm in both modes.
 */
export function SpotlightCard({
  children,
  radius = 400,
  className,
  ...props
}: {
  children: ReactNode;
  /** Radius of the halo that follows the cursor. */
  radius?: number;
  className?: string;
} & HTMLAttributes<HTMLDivElement>) {
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  function handleMouseMove({
    currentTarget,
    clientX,
    clientY,
  }: ReactMouseEvent<HTMLDivElement>) {
    const { left, top } = currentTarget.getBoundingClientRect();
    mouseX.set(clientX - left);
    mouseY.set(clientY - top);
  }

  const wash = useMotionTemplate`radial-gradient(${radius}px circle at ${mouseX}px ${mouseY}px, color-mix(in oklab, var(--color-lamp) 30%, transparent), transparent 75%)`;

  return (
    <div
      className={cn("group/spotlight relative", className)}
      onMouseMove={handleMouseMove}
      {...props}
    >
      {/* Painted after the static child in DOM order, so the halo sits over
          the card's surface and border instead of hiding underneath it. */}
      <motion.div
        aria-hidden
        className="pointer-events-none absolute -inset-px z-0 rounded-[inherit] opacity-0 transition-opacity duration-300 group-hover/spotlight:opacity-100"
        style={{ backgroundImage: wash }}
      />
      {children}
    </div>
  );
}
