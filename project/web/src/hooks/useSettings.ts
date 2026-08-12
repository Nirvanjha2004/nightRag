import { useCallback, useEffect, useState } from "react";
import type { PipelineConfig } from "@/lib/api";

const STORAGE_KEY = "nightrag.pipeline";

/** Pipeline knobs the user has changed. Anything absent uses the server default. */
export type PipelineSettings = Partial<PipelineConfig>;

function read(): PipelineSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as PipelineSettings) : {};
  } catch {
    return {};
  }
}

/**
 * Pipeline settings, persisted locally.
 *
 * Only overrides are stored, never a full copy of the server's defaults — so a
 * user who never touched the settings picks up new defaults when the server
 * changes them, instead of being pinned to whatever was current on their first
 * visit.
 */
export function usePipelineSettings() {
  const [settings, setSettings] = useState<PipelineSettings>(read);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch {
      /* storage unavailable — settings stay in memory for this session */
    }
  }, [settings]);

  const update = useCallback(<K extends keyof PipelineSettings>(key: K, value: PipelineSettings[K]) => {
    setSettings((current) => ({ ...current, [key]: value }));
  }, []);

  const reset = useCallback(() => setSettings({}), []);

  return { settings, update, reset, setSettings };
}
