import { clsx, type ClassValue } from "clsx";

/**
 * utils.ts — tiny shared helpers used across the UI.
 *
 * Most of these exist because a formatted number has to be readable at a
 * glance (chunk counts, relevance scores, elapsed times), and because a path
 * in the sources list is only useful once it is split into file + directory.
 */

/** Merge class names, dropping falsy values — the shadcn-style `cn` helper. */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}

/** 12 → "12"; 1234 → "1.2k"; 2345678 → "2.3M" — chunk counts in lists. */
export function formatCount(value: number): string {
  if (!Number.isFinite(value)) return "0";
  return new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

/**
 * A relevance score the way a reader expects it: whole numbers stay whole
 * (a reranker's "4"), fractions keep their significant digits (an RRF score
 * of "0.016").
 */
export function formatScore(score: number): string {
  if (!Number.isFinite(score)) return "–";
  if (Number.isInteger(score)) return String(score);
  return score.toFixed(3).replace(/\.?0+$/, "");
}

/** 850 → "850ms"; 2400 → "2.4s"; 90000 → "1m 30s". */
export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1).replace(/\.0$/, "")}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return rest === 0 ? `${minutes}m` : `${minutes}m ${rest}s`;
}

/** ISO timestamp → "14:32"; "" when unparseable (the UI treats "" as absent). */
export function formatTime(iso: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/**
 * Make a stage message or refinement read as a sentence. Capitalises the
 * first letter and never adds punctuation — callers add their own "." when
 * the phrasing calls for it.
 */
export function sentence(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return "";
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
}

/** "src/app/engine.py" → "engine.py" (handles both / and \\ separators). */
export function fileName(path: string): string {
  const segments = path.split(/[\\/]/).filter(Boolean);
  return segments.at(-1) ?? path;
}

/** "src/app/engine.py" → "src/app"; "" when the path has no directory. */
export function fileDir(path: string): string {
  const segments = path.split(/[\\/]/).filter(Boolean);
  segments.pop();
  return segments.join("/");
}
