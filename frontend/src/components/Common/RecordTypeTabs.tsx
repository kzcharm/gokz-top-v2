import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"

interface RecordTypeTabsProps {
  id?: string
  isProOnly: boolean
  onCheckedChange: (checked: boolean) => void
  ariaLabel?: string
  size?: "sm" | "default" | "lg"
  className?: string
  disabled?: boolean
}

const sizes = {
  sm: { list: "h-8", trigger: "px-2 text-xs" },
  default: { list: "h-9", trigger: "px-2 text-sm" },
  lg: { list: "h-10", trigger: "px-4 text-base" },
}

/** Shared NUB/PRO selector. Only the selected tab uses its record-type color. */
export function RecordTypeTabs({
  id,
  isProOnly,
  onCheckedChange,
  ariaLabel = "Run type",
  size = "default",
  className,
  disabled = false,
}: RecordTypeTabsProps) {
  return (
    <Tabs
      id={id}
      value={isProOnly ? "PRO" : "NUB"}
      onValueChange={(value) => onCheckedChange(value === "PRO")}
      className={cn("w-fit", className)}
    >
      <TabsList
        aria-label={ariaLabel}
        className={cn("border border-border/70", sizes[size].list)}
      >
        <TabsTrigger
          value="NUB"
          disabled={disabled}
          className={cn(
            "data-[state=active]:shadow-none data-[state=active]:bg-[#f3c40f] data-[state=active]:text-black dark:data-[state=active]:border-transparent dark:data-[state=active]:bg-[#f3c40f] dark:data-[state=active]:text-black",
            sizes[size].trigger,
          )}
        >
          NUB
        </TabsTrigger>
        <TabsTrigger
          value="PRO"
          disabled={disabled}
          className={cn(
            "data-[state=active]:shadow-none data-[state=active]:bg-[#3598db] data-[state=active]:text-white dark:data-[state=active]:border-transparent dark:data-[state=active]:bg-[#3598db] dark:data-[state=active]:text-white",
            sizes[size].trigger,
          )}
        >
          PRO
        </TabsTrigger>
      </TabsList>
    </Tabs>
  )
}
