import { useCallback, useEffect, useState } from "react";

/** Night is the design's home; day is the same lamp over paper. */
export type Theme = "night" | "day";

const STORAGE_KEY = "nightrag.theme";

function currentTheme(): Theme {
  return document.documentElement.getAttribute("data-theme") === "day" ? "day" : "night";
}

/**
 * Reads the theme the inline script in index.html already applied, and writes
 * changes back to both the DOM and localStorage. The initial value is never
 * computed here — doing so would repaint after first paint and flash.
 */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(currentTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* private mode — the theme still applies for this session */
    }
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((current) => (current === "night" ? "day" : "night"));
  }, []);

  return { theme, toggle };
}
