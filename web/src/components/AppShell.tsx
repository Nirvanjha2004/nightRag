import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { Moon, Sun } from "lucide-react";
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
 * which corpus the question will be asked of — as a readout rather than a
 * setting buried in a menu.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-dvh flex-col bg-ink">
      <InstrumentBar />
      <main id="main" className="min-h-0 flex-1 overflow-hidden">
        {children}
      </main>
    </div>
  );
}

function InstrumentBar() {
  const { theme, toggle } = useTheme();
  const { health } = useHealth();

  const chunks = health?.collections.reduce((total, c) => total + c.points, 0) ?? 0;

  return (
    <header className="flex shrink-0 items-center gap-3 border-b border-rule bg-panel px-3 sm:px-4">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-control focus:bg-lamp focus:px-3 focus:py-2 focus:text-sm focus:text-on-lamp"
      >
        Skip to content
      </a>

      {/* Wordmark. The lamp sits inside the O of Night as a moon — the only
          place the brand mark appears, and it doubles as the health light. */}
      <div className="flex items-center gap-2.5 py-3 pr-1">
        <Lamp lit={Boolean(health) && (health?.missing_keys.length ?? 1) === 0} />
        <p className="display text-[0.9375rem] font-bold tracking-tight text-moon">
          Night<span className="text-moon-3">Rag</span>
        </p>
      </div>

      <span aria-hidden className="hidden h-6 w-px bg-rule sm:block" />

      <nav aria-label="Main" className="flex items-center gap-0.5">
        {NAV.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "relative px-2.5 py-4 text-[0.8125rem] font-medium transition-colors sm:px-3",
                isActive ? "text-moon" : "text-moon-3 hover:text-moon-2",
              )
            }
          >
            {({ isActive }) => (
              <>
                {label}
                {/* The active tab is underlit, not just recoloured. */}
                <span
                  aria-hidden
                  className={cn(
                    "absolute inset-x-2 bottom-0 h-0.5 rounded-pill transition-opacity",
                    isActive ? "bg-lamp opacity-100" : "opacity-0",
                  )}
                />
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-2">
        {health && (
          <p className="hidden text-right sm:block">
            <span className="eyebrow block leading-tight">Corpus</span>
            <span className="tally text-xs text-moon-2">
              {formatCount(chunks)} chunks · {health.collections.length} collection
              {health.collections.length === 1 ? "" : "s"}
            </span>
          </p>
        )}

        <button
          type="button"
          onClick={toggle}
          aria-label={`Switch to ${theme === "night" ? "day" : "night"} theme`}
          className="rounded-control p-2 text-moon-3 transition-colors hover:bg-panel-2 hover:text-moon"
        >
          {theme === "night" ? (
            <Sun aria-hidden className="size-4" />
          ) : (
            <Moon aria-hidden className="size-4" />
          )}
        </button>
      </div>
    </header>
  );
}

/** The brand mark: a lamp that is dark until the server is actually usable. */
function Lamp({ lit }: { lit: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "relative flex size-7 items-center justify-center rounded-control border transition-colors",
        lit ? "border-lamp-line bg-lamp-soft" : "border-rule bg-panel-2",
      )}
    >
      <span
        className={cn(
          "size-2.5 rounded-pill transition-colors",
          lit ? "bg-lamp shadow-[0_0_12px_2px_rgba(255,180,84,0.55)]" : "bg-rule-strong",
        )}
      />
    </span>
  );
}
