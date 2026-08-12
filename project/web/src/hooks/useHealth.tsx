import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, type Health } from "@/lib/api";

interface HealthState {
  health: Health | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const HealthContext = createContext<HealthState | null>(null);

/**
 * Server status, shared by every screen.
 *
 * One fetch answers three questions the whole UI depends on: are the API keys
 * configured, which collections exist, and what are the pipeline defaults. It
 * is refreshed explicitly after ingestion rather than polled — nothing changes
 * on the server unless this UI changed it.
 */
export function HealthProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setHealth(await api.health());
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not reach the server.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({ health, loading, error, refresh }),
    [health, loading, error, refresh],
  );

  return <HealthContext.Provider value={value}>{children}</HealthContext.Provider>;
}

export function useHealth(): HealthState {
  const context = useContext(HealthContext);
  if (!context) throw new Error("useHealth must be used inside <HealthProvider>");
  return context;
}
