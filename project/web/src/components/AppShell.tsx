import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import {
  Boxes,
  Database,
  MessagesSquare,
  Moon,
  Sliders,
  Sun,
  type LucideIcon,
} from "lucide-react";
import { useHealth } from "@/hooks/useHealth";
import { useTheme } from "@/hooks/useTheme";
import { cn, formatCount } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

const NAV: NavItem[] = [
  { to: "/", label: "Ask", icon: MessagesSquare },
  { to: "/corpus", label: "Corpus", icon: Database },
  { to: "/settings", label: "Settings", icon: Sliders },
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-dvh flex-col bg-canvas md:flex-row">
      <Sidebar />
      <main id="main" className="min-w-0 flex-1 overflow-hidden">
        {children}
      </main>
    </div>
  );
}

function Sidebar() {
  const { theme, toggle } = useTheme();
  const { health } = useHealth();

  const points = health?.collections.reduce((total, c) => total + c.points, 0) ?? 0;

  return (
    <header
      className={cn(
        "flex shrink-0 items-center gap-2 border-b border-line bg-surface px-3 py-2",
        "md:h-dvh md:w-60 md:flex-col md:items-stretch md:gap-0 md:border-b-0 md:border-r md:px-3 md:py-4",
      )}
    >
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-control focus:bg-accent focus:px-3 focus:py-2 focus:text-sm focus:text-fg-inverse"
      >
        Skip to content
      </a>

      <div className="flex min-w-0 items-center gap-2.5 md:px-2 md:pb-6">
        <span
          aria-hidden
          className="flex size-8 shrink-0 items-center justify-center rounded-control border border-accent-line bg-accent-soft text-accent"
        >
          <Boxes className="size-4" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold tracking-tight text-fg">NightRag</p>
          <p className="hidden truncate text-[0.6875rem] text-fg-subtle md:block">
            {health ? `v${health.version} · ${formatCount(points)} chunks` : "connecting…"}
          </p>
        </div>
      </div>

      <nav aria-label="Main" className="ml-auto flex gap-1 md:ml-0 md:flex-1 md:flex-col md:gap-0.5">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-control px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-accent-soft text-accent"
                  : "text-fg-muted hover:bg-surface-hover hover:text-fg",
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon aria-hidden className="size-4 shrink-0" />
                <span className="hidden md:inline">{label}</span>
                <span className="sr-only md:hidden">{label}</span>
                {/* Active state is carried by the bar too, not colour alone. */}
                {isActive && (
                  <span aria-hidden className="ml-auto hidden h-4 w-0.5 rounded-pill bg-accent md:block" />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <button
        type="button"
        onClick={toggle}
        aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
        className={cn(
          "flex items-center gap-2.5 rounded-control px-3 py-2 text-sm font-medium",
          "text-fg-muted transition-colors hover:bg-surface-hover hover:text-fg",
        )}
      >
        {theme === "dark" ? (
          <Sun aria-hidden className="size-4" />
        ) : (
          <Moon aria-hidden className="size-4" />
        )}
        <span className="hidden md:inline">{theme === "dark" ? "Light" : "Dark"} theme</span>
      </button>
    </header>
  );
}
