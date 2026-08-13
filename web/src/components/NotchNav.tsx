import { NavLink } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Ask", end: true },
  { to: "/corpus", label: "Corpus" },
  { to: "/settings", label: "Settings" },
];

/**
 * The navigation, rendered as Aceternity's Notch adapted to the instrument
 * bar: a rounded glass pill whose active tab is a copper well that springs
 * from link to link. The pill itself rises and un-blurs into place on mount,
 * the same reveal the Notch uses — quieted for reduced-motion readers.
 *
 * Everything is on the warm tokens: the well is `lamp-soft` (a copper-tinted
 * surface in both themes), the text turns `lamp` when active, and the pill
 * container reuses the glass tokens so it blurs the washes behind it.
 */
export function NotchNav() {
  const reduced = useReducedMotion();

  return (
    <motion.nav
      aria-label="Main"
      initial={reduced ? false : { opacity: 0, y: 8, filter: "blur(6px)" }}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      transition={{ type: "spring", stiffness: 380, damping: 34 }}
      className="flex h-9 items-center gap-0.5 rounded-full border border-white/10 bg-glass-well/70 p-1 ring-1 ring-inset ring-white/5 backdrop-blur-2xl"
    >
      {NAV.map(({ to, label, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            cn(
              "relative flex h-full items-center rounded-full px-3 text-[0.8125rem] font-medium transition-colors sm:px-3.5",
              isActive ? "text-lamp" : "text-moon-3 hover:text-moon-2",
            )
          }
        >
          {({ isActive }) => (
            <>
              {/* One shared layoutId, so the active well slides between tabs
                  instead of flashing a new one — the Notch's signature move. */}
              {isActive && (
                <motion.span
                  layoutId="notch-active"
                  transition={{ type: "spring", stiffness: 420, damping: 36 }}
                  className="absolute inset-0 rounded-full bg-lamp-soft ring-1 ring-inset ring-lamp-line/40"
                />
              )}
              <span className="relative z-10">{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </motion.nav>
  );
}
