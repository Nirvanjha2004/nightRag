import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light";

const STORAGE_KEY = "nightrag.theme";

function currentTheme(): Theme {
  const attribute = document.documentElement.getAttribute("data-theme");
  return attribute === "light" ? "light" : "dark";
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
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  }, []);

  return { theme, toggle };
}
