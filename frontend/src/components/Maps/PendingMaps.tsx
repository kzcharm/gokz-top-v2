import { Skeleton } from "@/components/ui/skeleton"

export function PendingMaps() {
  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <Skeleton className="h-9 w-28" />
        <Skeleton className="h-5 w-full max-w-2xl" />
        <Skeleton className="h-4 w-56" />
      </div>

      <div className="rounded-2xl border border-border/70 p-4 sm:p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <Skeleton className="h-10 w-full lg:max-w-md" />
          <Skeleton className="h-10 w-full sm:w-64" />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {Array.from({ length: 8 }).map((_, index) => (
          <Skeleton key={index} className="aspect-[16/14] w-full rounded-xl" />
        ))}
      </div>
    </div>
  )
}
