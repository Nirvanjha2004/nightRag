import type { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Moon, Server, Sun } from "lucide-react";
import type { Health } from "@/lib/api";
import { useHealth } from "@/hooks/useHealth";
import { useTheme } from "@/hooks/useTheme";
import { cn, formatCount } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Ask" },
  { to: "/corpus", label: "Corpus" },
  { to: "/settings", label: "Settings" },
];

/**
 * A thin instrument bar over a full-width workbench.
 *
 * No sidebar: the screen below has to carry an answer and its evidence side by
 * side, and a rail of icons would spend 15rem of that on three links. The bar
 * instead carries the one piece of state a reader must always be able to see —
 * which corpus the question will be asked of — as a telemetry chip rather than
 * a setting buried in a menu.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const reduced = useReducedMotion();

  return (
    <div className="flex h-dvh flex-col bg-ink">
      <InstrumentBar />

      <main id="main" className="min-h-0 flex-1 overflow-hidden">
        {/* Pages share one entrance: a short rise. They are keyed by route so
            switching tabs reads as the next screen arriving, not a snap. */}
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={location.pathname}
            initial={reduced ? false : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduced ? undefined : { opacity: 0, y: -4 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            className="h-full"
          >
            {children}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}

function InstrumentBar() {
  const { theme, toggle } = useTheme();
  const { health } = useHealth();
  const lit = Boolean(health) && (health?.missing_keys.length ?? 1) === 0;

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b border-rule bg-nav px-3 sm:gap-3 sm:px-5">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-control focus:bg-lamp focus:px-3 focus:py-2 focus:text-sm focus:text-on-lamp"
      >
        Skip to content
      </a>

      {/* Wordmark. The lamp sits inside the O of Night as a moon — the only
          place the brand mark appears, and it doubles as the health light. */}
      <div className="flex h-full items-center">
        <BrandMark lit={lit} />
      </div>

      <span aria-hidden className="hidden h-5 w-px bg-rule sm:block" />

      <nav aria-label="Main" className="flex h-full items-center gap-0.5">
        {NAV.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "relative flex h-full items-center px-2.5 text-[0.8125rem] font-medium transition-colors sm:px-3.5",
                isActive ? "text-moon" : "text-moon-3 hover:text-moon-2",
              )
            }
          >
            {({ isActive }) => (
              <>
                {/* The active tab sits on a soft well with the lamp underlit.
                    Both shapes share a layoutId, so switching tabs slides the
                    indicator between them instead of flashing a new one. */}
                {isActive && (
                  <motion.span
                    layoutId="nav-well"
                    transition={{ type: "spring", stiffness: 420, damping: 36 }}
                    className="absolute inset-x-1.5 inset-y-1.5 rounded-control bg-panel"
                  />
                )}
                {isActive && (
                  <motion.span
                    layoutId="nav-accent"
                    transition={{ type: "spring", stiffness: 420, damping: 36 }}
                    className="absolute inset-x-2.5 bottom-0 h-0.5 rounded-pill bg-lamp"
                  />
                )}
                <span className="relative z-10">{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-2.5">
        {health && <CorpusStatus health={health} />}
        <ThemeToggle theme={theme} toggle={toggle} />
      </div>
    </header>
  );
}

/**
 * The brand mark: a lamp that is dark until the server is actually usable.
 * A lozenge rather than a square — the one rotated corner is the whole
 * identity — with the lit lamp glowing only in night, and a faint ring that
 * appears on hover to keep the mark alive without animating it constantly.
 */
function BrandMark({ lit }: { lit: boolean }) {
  return (
    <div
      className="group flex cursor-default items-center gap-2.5 pr-1"
      title={lit ? "Server ready" : "Server unavailable"}
    >
      <span
        aria-hidden
        className={cn(
          "relative flex size-7 items-center justify-center rounded-[0.4375rem] border transition-all duration-300",
          lit ? "border-lamp-line bg-lamp-soft" : "border-rule bg-panel-2",
          "group-hover:scale-[1.05] group-hover:border-lamp-line",
        )}
      >
        <span
          className={cn(
            "size-2.5 rounded-pill transition-all duration-300",
            lit ? "bg-lamp shadow-[var(--glow-dot)]" : "bg-rule-strong",
          )}
        />
        {lit && (
          <span className="pointer-events-none absolute inset-0 rounded-[0.4375rem] border border-lamp/25 opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
        )}
      </span>
      <p className="display text-[0.9375rem] font-bold tracking-tight text-moon">
        Night<span className="text-moon-3">Rag</span>
      </p>
    </div>
  );
}

/**
 * Corpus telemetry, compact: a live dot, the chunk count and the collection
 * count, with the breakdown one hover or focus away. It is a readout, not a
 * control — the button exists so keyboard users can reach the detail panel.
 */
function CorpusStatus({ health }: { health: Health }) {
  const chunks = health.collections.reduce((total, c) => total + c.points, 0);
  const ready = health.missing_keys.length === 0;
  const plural = health.collections.length === 1 ? "collection" : "collections";

  return (
    <div className="group relative hidden sm:block">
      <button
        type="button"
        aria-label={`Corpus status: ${formatCount(chunks)} chunks across ${health.collections.length} ${plural}`}
        className="flex h-8 items-center gap-2 rounded-control px-2 text-[0.6875rem] text-moon-3 transition-colors hover:text-moon-2"
      >
        <span className="relative flex size-1.5" aria-hidden>
          {ready && <span className="status-ping absolute inline-flex size-full rounded-pill bg-keep" />}
          <span
            className={cn(
              "relative inline-flex size-1.5 rounded-pill",
              ready ? "bg-keep" : "bg-lamp",
            )}
          />
        </span>
        <span className="tally tabular-nums text-moon-2">{formatCount(chunks)}</span>
        <span className="hidden md:inline">chunks</span>
        <span aria-hidden className="hidden h-3 w-px bg-rule md:block" />
        <span className="tally tabular-nums text-moon-2">{health.collections.length}</span>
        <span className="hidden md:inline">{plural}</span>
      </button>

      {/* The detail panel: collection names with counts, plus where the index
          lives. Pointer-events-none until hovered so it never traps the
          cursor on the way to something else. */}
      <div
        role="tooltip"
        className="pointer-events-none absolute right-0 top-full z-40 mt-2 w-72 origin-top-right translate-y-1 scale-[0.98] rounded-panel border border-rule bg-panel opacity-0 shadow-[var(--shadow-float)] transition-all duration-150 group-hover:pointer-events-auto group-hover:translate-y-0 group-hover:scale-100 group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:translate-y-0 group-focus-within:scale-100 group-focus-within:opacity-100"
      >
        <p className="eyebrow px-3 pt-3">Corpus</p>
        <ul className="mt-1.5 max-h-44 overflow-y-auto px-3 pb-2.5">
          {health.collections.length === 0 ? (
            <li className="py-1 text-xs text-moon-3">Nothing indexed yet.</li>
          ) : (
            health.collections.map((collection) => (
              <li
                key={collection.name}
                className="flex items-baseline justify-between gap-3 rounded-control px-1 py-1"
              >
                <span className="truncate font-mono text-xs text-moon">{collection.name}</span>
                <span className="tally shrink-0 text-[0.6875rem] tabular-nums text-moon-3">
                  {formatCount(collection.points)}
                </span>
              </li>
            ))
          )}
        </ul>
        <div className="flex items-center justify-between gap-3 border-t border-rule px-3 py-2 text-[0.6875rem] text-moon-3">
          <span className="flex min-w-0 items-center gap-1.5">
            <Server aria-hidden className="size-3 shrink-0" />
            <span className="truncate">{health.storage}</span>
          </span>
          <span className="tally shrink-0 tabular-nums">v{health.version}</span>
        </div>
      </div>
    </div>
  );
}

/**
 * Theme switch. The icons crossfade and spin into place rather than swapping,
 * so the change reads as a small ceremony instead of a blink. The page
 * surface itself eases through the same transition (see body in index.css).
 */
function ThemeToggle({ theme, toggle }: { theme: string; toggle: () => void }) {
  const night = theme === "night";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${night ? "day" : "night"} theme`}
      className="flex size-8 items-center justify-center overflow-hidden rounded-control border border-rule bg-panel text-moon-2 transition-colors hover:border-rule-strong hover:text-moon"
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={theme}
          initial={{ rotate: -90, opacity: 0, scale: 0.6 }}
          animate={{ rotate: 0, opacity: 1, scale: 1 }}
          exit={{ rotate: 90, opacity: 0, scale: 0.6 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="flex"
        >
          {night ? (
            <Sun aria-hidden className="size-4" />
          ) : (
            <Moon aria-hidden className="size-4" />
          )}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}
