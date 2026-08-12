import { cn } from "@/lib/utils";

/** Loading placeholder shaped like the content it replaces. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn("animate-pulse rounded-control bg-panel-2", className)}
    />
  );
}

/** The list-shaped variant, used while collections and jobs load. */
export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-hidden>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="flex items-center gap-3 rounded-control border border-rule p-3">
          <Skeleton className="size-8 shrink-0 rounded-pill" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3 w-1/3" />
            <Skeleton className="h-2.5 w-1/4" />
          </div>
        </div>
      ))}
    </div>
  );
}
